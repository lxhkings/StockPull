"""
intraday_updater_us.py — 美股分钟级行情拉取（15m / 1h）

数据源: yfinance 免费 tier
存储: prices_intraday 表
Sync: sync_log data_type='intraday_15m'|'intraday_60m'
"""

from __future__ import annotations

import logging
import random
import signal
import time
from datetime import date, timedelta
from typing import Optional

import pandas as pd
import yfinance as yf

from config import (
    YF_BATCH_DELAY_BASE,
    YF_BATCH_DELAY_JITTER,
    YF_BATCH_SIZE,
    YF_RETRY_COUNT,
    YF_TIMEOUT,
)
from data.base import to_float, to_int
from db import get_conn, get_last_sync, set_sync_error, set_sync_ok

log = logging.getLogger(__name__)

# interval → yfinance 参数字符串
YF_INTERVAL_MAP: dict[str, str] = {
    "15m": "15m",
    "1h":  "60m",
}

# interval → yfinance 免费 tier 最大可拉天数
INTERVAL_LOOKBACK_DAYS: dict[str, int] = {
    "15m": 60,
    "1h":  730,
}

SUPPORTED_INTERVALS = list(YF_INTERVAL_MAP.keys())


def _sync_type(interval: str) -> str:
    """'15m' → 'intraday_15m', '1h' → 'intraday_60m'"""
    return f"intraday_{YF_INTERVAL_MAP[interval]}"


def _yf_symbol(ticker: str) -> str:
    """DB ticker → yfinance symbol: BRK.B → BRK-B"""
    return ticker.upper().replace(".", "-")


def _normalize_frame(ticker: str, interval: str, sub: pd.DataFrame) -> pd.DataFrame:
    """yfinance 单 ticker 子表 → 标准列 [ticker, interval, datetime, open, high, low, close, volume]"""
    cols = ["ticker", "interval", "datetime", "open", "high", "low", "close", "volume"]
    if sub is None or sub.empty:
        return pd.DataFrame(columns=cols)

    df = sub.reset_index()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df.columns = [str(c).lower() for c in df.columns]

    for cand in ("datetime", "date", "index"):
        if cand in df.columns:
            df = df.rename(columns={cand: "datetime"})
            break

    df["datetime"] = pd.to_datetime(df["datetime"])
    # 剥除时区，MySQL DATETIME 无时区（yfinance 返回 UTC）
    if df["datetime"].dt.tz is not None:
        df["datetime"] = df["datetime"].dt.tz_convert("UTC").dt.tz_localize(None)

    df["ticker"] = ticker
    df["interval"] = interval
    df = df.dropna(subset=["datetime", "close"])
    return df[cols].sort_values("datetime").reset_index(drop=True)


def _save_rows(conn, df: pd.DataFrame) -> int:
    """INSERT IGNORE 写 prices_intraday，PRIMARY KEY 自动去重"""
    sql = """
        INSERT IGNORE INTO prices_intraday
          (ticker, `interval`, datetime, open, high, low, close, volume)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """
    rows = [
        (
            r.ticker,
            r.interval,
            r.datetime,
            to_float(getattr(r, "open", None)),
            to_float(getattr(r, "high", None)),
            to_float(getattr(r, "low", None)),
            to_float(r.close),
            to_int(getattr(r, "volume", None)),
        )
        for r in df.itertuples(index=False)
    ]
    with conn.cursor() as cur:
        cur.executemany(sql, rows)
    conn.commit()
    return len(rows)


def update_intraday(interval: str, full_rebase: bool = False) -> dict[str, str]:
    """批量增量拉取美股 intraday，写入 prices_intraday。

    Args:
        interval: '15m' 或 '1h'
        full_rebase: True 时忽略 sync_log，从 floor_date 全量拉取
    Returns:
        {ticker: 'ok' | 'no_data' | 'error: <msg>'}
    """
    if interval not in SUPPORTED_INTERVALS:
        raise ValueError(f"Unsupported interval: {interval}. Supported: {SUPPORTED_INTERVALS}")

    from data.market_us import list_active_tickers
    tickers = list_active_tickers()

    lookback_days = INTERVAL_LOOKBACK_DAYS[interval]
    floor_date = date.today() - timedelta(days=lookback_days - 1)
    today = date.today()

    result: dict[str, str] = {}
    conn = get_conn()
    try:
        sync_type = _sync_type(interval)

        pending: list[tuple[str, date]] = []
        for t in tickers:
            if full_rebase:
                pending.append((t, floor_date))
            else:
                last = get_last_sync(conn, t, sync_type)
                if last is None:
                    pending.append((t, floor_date))
                elif last >= today:
                    result[t] = "ok"
                else:
                    start = max(last + timedelta(days=1), floor_date)
                    pending.append((t, start))

        if not pending:
            log.info(f"[intraday {interval}] 所有 ticker 已是最新，无需更新")
            return result

        log.info(f"[intraday {interval}] 需更新 {len(pending)} 只 ticker")

        pending.sort(key=lambda x: x[1])

        for i in range(0, len(pending), YF_BATCH_SIZE):
            batch_pairs = pending[i:i + YF_BATCH_SIZE]
            batch = [t for t, _ in batch_pairs]
            batch_start = min(s for _, s in batch_pairs)
            _download_and_save(conn, batch, interval, batch_start, result)
            if i + YF_BATCH_SIZE < len(pending):
                delay = YF_BATCH_DELAY_BASE + random.uniform(
                    -YF_BATCH_DELAY_JITTER, YF_BATCH_DELAY_JITTER
                )
                log.debug(f"[intraday {interval}] 等待 {delay:.1f}s")
                time.sleep(delay)

        return result
    finally:
        conn.close()


def _download_and_save(
    conn,
    tickers: list[str],
    interval: str,
    start_date: date,
    result: dict[str, str],
) -> None:
    """下载一批 ticker 的 intraday 数据并保存到 prices_intraday。"""
    end_date = date.today() + timedelta(days=1)
    yf_interval = YF_INTERVAL_MAP[interval]
    yf_symbols = [_yf_symbol(t) for t in tickers]
    sync_type = _sync_type(interval)

    log.info(f"[intraday {interval}] 下载 {len(tickers)} 只，{start_date} ~ {date.today()}")

    df = None
    last_exc: Optional[Exception] = None
    for attempt in range(YF_RETRY_COUNT):
        try:
            signal.signal(signal.SIGINT, signal.SIG_DFL)
            df = yf.download(
                tickers=yf_symbols,
                start=start_date.strftime("%Y-%m-%d"),
                end=end_date.strftime("%Y-%m-%d"),
                interval=yf_interval,
                group_by="ticker",
                auto_adjust=False,
                actions=False,
                threads=False,
                progress=False,
                timeout=YF_TIMEOUT,
            )
            last_exc = None
            break
        except Exception as e:
            last_exc = e
            if attempt < YF_RETRY_COUNT - 1:
                backoff = 5 * (3 ** attempt)
                log.warning(f"yf.download attempt {attempt + 1} failed, retry in {backoff}s: {e}")
                time.sleep(backoff)

    if last_exc is not None:
        msg = f"yfinance failed after {YF_RETRY_COUNT} retries: {last_exc}"
        log.error(msg)
        for t in tickers:
            set_sync_error(conn, t, sync_type, msg)
            result[t] = f"error: {last_exc}"
        return

    # yfinance: 2+ tickers → MultiIndex DataFrame; single ticker → plain DataFrame
    is_multi = df is not None and not df.empty and isinstance(df.columns, pd.MultiIndex)
    top_level = set(df.columns.get_level_values(0)) if is_multi else set()

    for t in tickers:
        yf_t = _yf_symbol(t)
        if is_multi:
            if yf_t not in top_level:
                log.warning(f"[{t}] not in yfinance response")
                set_sync_error(conn, t, sync_type, "yfinance: ticker not in response")
                result[t] = "no_data"
                continue
            sub = df[yf_t]
        elif df is not None and not df.empty and len(tickers) == 1:
            sub = df  # single-ticker plain DataFrame
        else:
            log.warning(f"[{t}] no data in response")
            set_sync_error(conn, t, sync_type, "yfinance: empty or unexpected response")
            result[t] = "no_data"
            continue

        normalized = _normalize_frame(t, interval, sub)
        if normalized.empty:
            log.warning(f"[{t}] empty frame")
            set_sync_error(conn, t, sync_type, "yfinance: empty frame")
            result[t] = "no_data"
            continue
        try:
            rows_inserted = _save_rows(conn, normalized)
            new_last = normalized["datetime"].max().date()
            set_sync_ok(conn, t, sync_type, new_last, rows_inserted)
            result[t] = "ok"
            log.info(f"[{t}] 写入 {rows_inserted} 条，最新={new_last}")
        except Exception as e:
            log.error(f"[{t}] 写库失败: {e}")
            set_sync_error(conn, t, sync_type, str(e))
            result[t] = f"error: {e}"
