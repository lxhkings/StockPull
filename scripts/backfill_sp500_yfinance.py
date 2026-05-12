#!/usr/bin/env python3
"""SP500 backfill via yfinance - 参照 stock_updater.py 逻辑"""

import yfinance as yf
import pymysql
import time
import pandas as pd
import logging
from datetime import date, datetime, timedelta
from typing import Dict

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
log = logging.getLogger(__name__)

conn = pymysql.connect(
    host='192.168.8.9', port=3306, user='root',
    password='18620001807@Aa', database='stocks'
)

# Get SP500 tickers
with conn.cursor() as cur:
    cur.execute("SELECT DISTINCT ticker FROM index_constituents WHERE index_id='SP500' ORDER BY ticker")
    tickers = [r[0] for r in cur.fetchall()]

log.info(f'SP500: {len(tickers)} tickers')

# Constants (from stock_updater.py / config.py)
HISTORY_YEARS = 5
YF_LOOKBACK_DAYS = 7
YF_BATCH_SIZE = 20
YF_RETRY_COUNT = 3
YF_TIMEOUT = 30
YF_BATCH_DELAY = 2.0


def _yf_symbol(ticker: str) -> str:
    """DB ticker → yfinance ticker"""
    return ticker.upper().replace(".", "-")


def get_last_sync(conn, ticker: str, data_type: str):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT last_date FROM sync_log WHERE ticker=%s AND data_type=%s",
            (ticker, data_type)
        )
        r = cur.fetchone()
        return r[0] if r else None


def set_sync_ok(conn, ticker: str, data_type: str, last_date: date, rows: int):
    now = datetime.now()
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO sync_log (ticker, data_type, last_date, last_run, rows_added, status, message)
            VALUES (%s, %s, %s, %s, %s, 'ok', '')
            ON DUPLICATE KEY UPDATE
                last_date=VALUES(last_date), last_run=VALUES(last_run),
                rows_added=VALUES(rows_added), status=VALUES(status), message=VALUES(message)
        """, (ticker, data_type, last_date, now, rows))
    conn.commit()


def set_sync_error(conn, ticker: str, data_type: str, msg: str):
    now = datetime.now()
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO sync_log (ticker, data_type, last_date, last_run, rows_added, status, message)
            VALUES (%s, %s, NULL, %s, 0, 'error', %s)
            ON DUPLICATE KEY UPDATE
                last_run=VALUES(last_run), status=VALUES(status), message=VALUES(message)
        """, (ticker, data_type, now, msg))
    conn.commit()


def _normalize_yf_frame(ticker: str, sub: pd.DataFrame) -> pd.DataFrame:
    """yfinance 单 ticker 子表 → [ticker, date, open, high, low, close, volume]"""
    cols = ["ticker", "date", "open", "high", "low", "close", "volume"]
    if sub is None or sub.empty:
        return pd.DataFrame(columns=cols)

    df = sub.reset_index()
    df.columns = [str(c).lower() for c in df.columns]

    if "date" not in df.columns:
        for cand in ("datetime", "index"):
            if cand in df.columns:
                df = df.rename(columns={cand: "date"})
                break

    df["date"] = pd.to_datetime(df["date"]).dt.date
    df["ticker"] = ticker
    df = df.dropna(subset=["date", "close"])
    df = df[cols].sort_values("date").reset_index(drop=True)
    return df


def _save_prices(conn, ticker: str, df: pd.DataFrame) -> int:
    """INSERT IGNORE 写 prices 表"""
    sql = "INSERT IGNORE INTO prices (ticker, date, open, high, low, close, volume) VALUES (%s, %s, %s, %s, %s, %s, %s)"
    rows = [
        (r.ticker, r.date,
         float(r.open) if pd.notna(r.open) else 0,
         float(r.high) if pd.notna(r.high) else 0,
         float(r.low) if pd.notna(r.low) else 0,
         float(r.close) if pd.notna(r.close) else 0,
         int(r.volume) if pd.notna(r.volume) else 0)
        for r in df.itertuples(index=False)
    ]
    with conn.cursor() as cur:
        cur.executemany(sql, rows)
    conn.commit()
    return len(rows)


# 批量入口
def update_prices_batch(tickers, full_rebase=False) -> Dict[str, str]:
    if not tickers:
        return {}

    # 计算每只股票的开始日期
    per_ticker_start = {}
    START_DATE = date(2010, 1, 1)
    for t in tickers:
        if full_rebase:
            start_dt = START_DATE
        else:
            last = get_last_sync(conn, t, "price")
            if last is None:
                start_dt = (datetime.today() - timedelta(days=365 * HISTORY_YEARS)).date()
            else:
                start_dt = last - timedelta(days=YF_LOOKBACK_DAYS)
        per_ticker_start[t] = start_dt

    batch_start = min(per_ticker_start.values())
    end_dt = (datetime.today() + timedelta(days=1)).date()
    yf_symbols = [_yf_symbol(t) for t in tickers]

    log.info(f"Batch: {batch_start} → {end_dt}, {len(tickers)} tickers")

    # 带重试的下载
    df = None
    last_exc = None
    for attempt in range(YF_RETRY_COUNT):
        try:
            df = yf.download(
                tickers=yf_symbols,
                start=batch_start.strftime("%Y-%m-%d"),
                end=end_dt.strftime("%Y-%m-%d"),
                interval="1d",
                group_by="ticker",
                auto_adjust=False,
                actions=False,
                threads=True,
                progress=False,
                timeout=YF_TIMEOUT,
                repair=False,
            )
            last_exc = None
            break
        except Exception as e:
            last_exc = e
            if attempt < YF_RETRY_COUNT - 1:
                backoff = 5 * (3 ** attempt)
                log.warning(f"yf.download 第 {attempt+1} 次失败，{backoff}s 后重试: {e}")
                time.sleep(backoff)

    result = {}
    if last_exc is not None:
        log.error(f"yfinance batch failed after {YF_RETRY_COUNT} retries: {last_exc}")
        for t in tickers:
            set_sync_error(conn, t, "price", str(last_exc))
            result[t] = f"error: {last_exc}"
        return result

    top_level = set()
    if df is not None and not df.empty and isinstance(df.columns, pd.MultiIndex):
        top_level = set(df.columns.get_level_values(0))

    for t in tickers:
        yf_t = _yf_symbol(t)
        if yf_t not in top_level:
            set_sync_error(conn, t, "price", "yfinance: ticker not in response")
            result[t] = "no_data"
            continue

        sub = df[yf_t]
        normalized = _normalize_yf_frame(t, sub)
        if normalized.empty:
            set_sync_error(conn, t, "price", "yfinance: empty frame")
            result[t] = "no_data"
            continue

        try:
            rows_inserted = _save_prices(conn, t, normalized)
            new_last = normalized["date"].max()
            set_sync_ok(conn, t, "price", new_last, rows_inserted)
            result[t] = "ok"
            log.info(f"[{t}] 写入 {rows_inserted} 条，最新={new_last}")
        except Exception as e:
            log.error(f"[{t}] 写库失败: {e}")
            set_sync_error(conn, t, "price", str(e))
            result[t] = f"error: {e}"

    return result


# 主循环：分批处理（全量回填）
log.info("=== Full rebase from 2010-01-01 ===")
for i in range(0, len(tickers), YF_BATCH_SIZE):
    batch = tickers[i:i+YF_BATCH_SIZE]
    log.info(f"=== Batch {i//YF_BATCH_SIZE + 1}/{(len(tickers)+YF_BATCH_SIZE-1)//YF_BATCH_SIZE} ===")
    update_prices_batch(batch, full_rebase=True)
    time.sleep(YF_BATCH_DELAY)

log.info("Done!")
conn.close()
