"""HK daily-K updater via yfinance."""

from __future__ import annotations

import logging
import time
from datetime import date, timedelta
from typing import Dict, List, Optional

import pandas as pd

from config import (
    START_DATE_HK, YF_LOOKBACK_DAYS,
)
from db import get_conn, get_last_sync, set_sync_ok, set_sync_error
from data.base import to_float, to_int
from data.yf_client import history_with_retry

log = logging.getLogger(__name__)


def update_prices_batch(tickers: List[str], full_rebase: bool = False, years: Optional[int] = None) -> Dict[str, str]:
    if not tickers:
        return {}
    today = date.today()
    end = today
    result: Dict[str, str] = {}

    conn = get_conn()
    try:
        for t in tickers:
            try:
                if full_rebase:
                    if years:
                        # 根据指定的年数计算起始日期
                        start = today - timedelta(days=365 * years)
                    else:
                        start = date.fromisoformat(START_DATE_HK)
                else:
                    last = get_last_sync(conn, t, "price")
                    if last is None:
                        start = date.fromisoformat(START_DATE_HK)
                    else:
                        start = last - timedelta(days=YF_LOOKBACK_DAYS)

                df = _fetch_one_yfinance(t, start, end)
                if df is None or df.empty:
                    set_sync_error(conn, t, "price", "yfinance: no data")
                    result[t] = "no_data"
                    continue

                rows = _save_prices(conn, df)
                set_sync_ok(conn, t, "price", df["date"].max(), rows)
                result[t] = "ok"
                log.info(f"[{t}] 写入 {rows} 行，{df['date'].min()} → {df['date'].max()}")
                time.sleep(1)  # yfinance rate limit
            except Exception as e:
                log.error(f"[{t}] 失败: {e}")
                set_sync_error(conn, t, "price", str(e))
                result[t] = f"error: {e}"
        return result
    finally:
        conn.close()


def _fetch_one_yfinance(ticker: str, start: date, end: date) -> pd.DataFrame:
    """Fetch HK stock via yfinance."""
    df = history_with_retry(
        ticker, start=start.isoformat(), end=end.isoformat(), context=f"[{ticker}] ",
    )
    if df is None or df.empty:
        return pd.DataFrame(columns=["ticker", "date", "open", "high", "low", "close", "volume"])

    df = df.reset_index()
    df["date"] = df["Date"].dt.date
    df = df.rename(columns={
        "Open": "open", "High": "high", "Low": "low",
        "Close": "close", "Volume": "volume"
    })
    df["ticker"] = ticker
    return df[["ticker", "date", "open", "high", "low", "close", "volume"]]


def _save_prices(conn, df: pd.DataFrame) -> int:
    """INSERT ... ON DUPLICATE KEY UPDATE so rebases overwrite cleanly."""
    sql = """
        INSERT INTO prices (ticker, date, open, high, low, close, volume)
        VALUES (%s,%s,%s,%s,%s,%s,%s)
        ON DUPLICATE KEY UPDATE
            open=VALUES(open), high=VALUES(high), low=VALUES(low),
            close=VALUES(close), volume=VALUES(volume)
    """
    rows = [
        (r.ticker, r.date,
         to_float(r.open), to_float(r.high), to_float(r.low),
         to_float(r.close), to_int(r.volume))
        for r in df.itertuples(index=False)
    ]
    with conn.cursor() as cur:
        cur.executemany(sql, rows)
    conn.commit()
    return len(rows)
