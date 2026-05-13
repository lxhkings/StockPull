#!/usr/bin/env python3
"""HK index backfill via yfinance - 使用 db.py 和 config.py"""

import yfinance as yf
import time
import pandas as pd
import logging
from datetime import date, timedelta
from typing import Dict

from db import get_conn, get_last_sync, set_sync_ok, set_sync_error
from config import DB, YF_RETRY_COUNT, YF_TIMEOUT, START_DATE_HK

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
log = logging.getLogger(__name__)

conn = get_conn()

# HK indices to backfill (db_ticker: yf_symbol)
INDEXES = {
    "HSI": "^HSI",
    "HSTECH": "3087.HK",
    "HSBI": "2800.HK",
}

log.info(f'HK indices: {list(INDEXES.keys())}')

HISTORY_YEARS = 15


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
    if full_rebase:
        start_dt = date.fromisoformat(START_DATE_HK)
    else:
        last = get_last_sync(conn, db_ticker, "price")
        if last:
            start_dt = last - timedelta(days=7)
        else:
            start_dt = date.today() - timedelta(days=365 * HISTORY_YEARS)

    end_dt = date.today() + timedelta(days=1)

    log.info(f"[{db_ticker}] {start_dt} → {end_dt}")

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