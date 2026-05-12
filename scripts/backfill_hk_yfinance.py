#!/usr/bin/env python3
"""HK index backfill via yfinance - HSI, HSTECH, HSBI"""

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

# HK indices to backfill (db_ticker: yf_symbol)
INDEXES = {
    "HSI": "^HSI",
    "HSTECH": "3087.HK",   # 恒生科技指数 ETF
    "HSBI": "2800.HK",     # 盈富基金 (追踪 HSCEI)
}

log.info(f'HK indices: {list(INDEXES.keys())}')

# Constants
HISTORY_YEARS = 15
YF_RETRY_COUNT = 3
YF_TIMEOUT = 30


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


def _save_prices(conn, ticker: str, df: pd.DataFrame) -> int:
    """INSERT IGNORE 写 prices 表"""
    sql = "INSERT IGNORE INTO prices (ticker, date, open, high, low, close, volume) VALUES (%s, %s, %s, %s, %s, %s, %s)"
    rows = [
        (ticker, r["date"],
         float(r["open"]) if pd.notna(r["open"]) else 0,
         float(r["high"]) if pd.notna(r["high"]) else 0,
         float(r["low"]) if pd.notna(r["low"]) else 0,
         float(r["close"]) if pd.notna(r["close"]) else 0,
         int(r["volume"]) if pd.notna(r["volume"]) else 0)
        for _, r in df.iterrows()
    ]
    with conn.cursor() as cur:
        cur.executemany(sql, rows)
    conn.commit()
    return len(rows)


def fetch_index(db_ticker: str, yf_symbol: str, full_rebase: bool = False) -> Dict:
    START_DATE = date(2010, 1, 1)

    if full_rebase:
        start_dt = START_DATE
    else:
        last = get_last_sync(conn, db_ticker, "price")
        if last:
            start_dt = last - timedelta(days=7)
        else:
            start_dt = (datetime.now() - timedelta(days=365 * HISTORY_YEARS)).date()

    end_dt = date.today() + timedelta(days=1)

    log.info(f"[{db_ticker}] {start_dt} → {end_dt}")

    # Try to fetch
    for attempt in range(YF_RETRY_COUNT):
        try:
            t = yf.Ticker(yf_symbol)
            df = t.history(start=start_dt.isoformat(), end=end_dt.isoformat())
            break
        except Exception as e:
            if attempt < YF_RETRY_COUNT - 1:
                time.sleep(5 * (3 ** attempt))
                continue
            log.error(f"[{db_ticker}] failed: {e}")
            set_sync_error(conn, db_ticker, "price", str(e))
            return {"status": "error", "msg": str(e)}

    if df is None or df.empty:
        log.warning(f"[{db_ticker}] no data")
        set_sync_error(conn, db_ticker, "price", "no data")
        return {"status": "no_data"}

    # Normalize
    df = df.reset_index()
    df["date"] = df["Date"].dt.date
    df = df.rename(columns={
        "Open": "open", "High": "high", "Low": "low",
        "Close": "close", "Volume": "volume"
    })
    df = df[["date", "open", "high", "low", "close", "volume"]].dropna(subset=["date", "close"])

    if df.empty:
        set_sync_error(conn, db_ticker, "price", "empty after clean")
        return {"status": "no_data"}

    rows = _save_prices(conn, db_ticker, df)
    new_last = df["date"].max()
    set_sync_ok(conn, db_ticker, "price", new_last, rows)
    log.info(f"[{db_ticker}] wrote {rows} rows, latest={new_last}")
    return {"status": "ok", "rows": rows}


log.info("=== Full rebase from 2010-01-01 ===")
for db_ticker, yf_symbol in INDEXES.items():
    fetch_index(db_ticker, yf_symbol, full_rebase=True)
    time.sleep(2)

log.info("Done!")
conn.close()
