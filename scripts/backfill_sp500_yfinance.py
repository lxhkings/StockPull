#!/usr/bin/env python3
"""SP500 backfill via yfinance - 使用 db.py 和 config.py"""

import yfinance as yf
import time
import pandas as pd
import logging
from datetime import date, datetime, timedelta
from typing import Dict

from db import get_conn, get_last_sync, set_sync_ok, set_sync_error
from config import DB, YF_RETRY_COUNT, YF_TIMEOUT, HISTORY_YEARS_US
from data.stock_updater_us import _yf_symbol, _normalize_yf_frame, _save_prices

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
log = logging.getLogger(__name__)

conn = get_conn()

# Get SP500 tickers
with conn.cursor() as cur:
    cur.execute("SELECT DISTINCT ticker FROM index_constituents WHERE index_id='SP500' ORDER BY ticker")
    tickers = [r[0] for r in cur.fetchall()]

log.info(f'SP500: {len(tickers)} tickers')

YF_BATCH_SIZE = 20
YF_BATCH_DELAY = 2.0
YF_LOOKBACK_DAYS = 7


def update_prices_batch(tickers, full_rebase=False) -> Dict[str, str]:
    if not tickers:
        return {}

    START_DATE = date(2010, 1, 1)
    per_ticker_start = {}
    for t in tickers:
        if full_rebase:
            start_dt = START_DATE
        else:
            last = get_last_sync(conn, t, "price")
            if last is None:
                start_dt = (datetime.today() - timedelta(days=365 * HISTORY_YEARS_US)).date()
            else:
                start_dt = last - timedelta(days=YF_LOOKBACK_DAYS)
        per_ticker_start[t] = start_dt

    batch_start = min(per_ticker_start.values())
    end_dt = (datetime.today() + timedelta(days=1)).date()
    yf_symbols = [_yf_symbol(t) for t in tickers]

    log.info(f"Batch: {batch_start} → {end_dt}, {len(tickers)} tickers")

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