"""A-share daily-K updater via akshare (post-adjusted, hfq).

Stores hfq close in `prices.close` (matches yfinance auto-adjusted convention
on the existing US data, even though current US data is raw — known v2 mismatch).
"""

from __future__ import annotations

import logging
import time
from datetime import date, datetime, timedelta
from typing import Dict, List

import akshare as ak
import efinance as ef
import pandas as pd

from config import (
    HISTORY_YEARS_CN, START_DATE_CN, YF_LOOKBACK_DAYS,
    AKSHARE_RETRY_COUNT, AKSHARE_RETRY_DELAY, AKSHARE_REQUEST_DELAY,
)
from db import get_conn, get_last_sync, set_sync_ok, set_sync_error
from data.base import to_float, to_int
from data.ticker_utils import to_akshare_a, to_efinance_a
from data.reconcile import reconcile_two_sources

log = logging.getLogger(__name__)


def update_prices_batch(tickers: List[str], full_rebase: bool = False) -> Dict[str, str]:
    """Pull daily K (hfq) for a list of A-share canonical tickers (e.g., 600519.SH).

    Args:
      tickers: canonical A-share tickers
      full_rebase: if True, ignore sync_log and pull from START_DATE_CN

    Returns: {ticker: status}
    """
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
                    start = date.fromisoformat(START_DATE_CN)
                else:
                    last = get_last_sync(conn, t, "price")
                    if last is None:
                        start = date.fromisoformat(START_DATE_CN)
                    else:
                        start = last - timedelta(days=YF_LOOKBACK_DAYS)

                df_a = _fetch_one_akshare_with_retry(t, start, end)
                is_backfill = full_rebase or last is None
                if is_backfill:
                    try:
                        df_b = _fetch_one_efinance(t, start, end)
                    except Exception as e:
                        log.warning(f"[{t}] efinance failed (continue with akshare): {e}")
                        df_b = pd.DataFrame(columns=df_a.columns)
                    df, mismatches = reconcile_two_sources(df_a, df_b)
                    if mismatches:
                        log.warning(f"[{t}] {len(mismatches)} reconcile mismatches (logged above)")
                else:
                    df = df_a

                if df is None or df.empty:
                    set_sync_error(conn, t, "price", "akshare: no data")
                    result[t] = "no_data"
                    continue

                rows = _save_prices(conn, df)
                set_sync_ok(conn, t, "price", df["date"].max(), rows)
                result[t] = "ok"
                log.info(f"[{t}] 写入 {rows} 行，{df['date'].min()} → {df['date'].max()}")
                time.sleep(AKSHARE_REQUEST_DELAY)
            except Exception as e:
                log.error(f"[{t}] 失败: {e}")
                set_sync_error(conn, t, "price", str(e))
                result[t] = f"error: {e}"
        return result
    finally:
        conn.close()


def _fetch_one_akshare_with_retry(ticker: str, start: date, end: date) -> pd.DataFrame:
    last_exc = None
    for attempt in range(AKSHARE_RETRY_COUNT):
        try:
            return _fetch_one_akshare(ticker, start, end)
        except Exception as e:
            last_exc = e
            if attempt < AKSHARE_RETRY_COUNT - 1:
                wait = AKSHARE_RETRY_DELAY * (2 ** attempt)
                log.warning(f"[{ticker}] akshare attempt {attempt+1} failed: {e}, retry in {wait}s")
                time.sleep(wait)
    raise last_exc


def _fetch_one_akshare(ticker: str, start: date, end: date) -> pd.DataFrame:
    code = to_akshare_a(ticker)
    raw = ak.stock_zh_a_hist(
        symbol=code, period="daily",
        start_date=start.strftime("%Y%m%d"),
        end_date=end.strftime("%Y%m%d"),
        adjust="hfq",
    )
    if raw is None or raw.empty:
        return pd.DataFrame(columns=["ticker", "date", "open", "high", "low", "close", "volume"])

    df = pd.DataFrame({
        "ticker": ticker,
        "date":   pd.to_datetime(raw["日期"]).dt.date,
        "open":   raw["开盘"].astype(float),
        "high":   raw["最高"].astype(float),
        "low":    raw["最低"].astype(float),
        "close":  raw["收盘"].astype(float),
        "volume": raw["成交量"].astype("int64"),
    })
    return df[["ticker", "date", "open", "high", "low", "close", "volume"]]


def _fetch_one_efinance(ticker: str, start: date, end: date) -> pd.DataFrame:
    """efinance A-share post-adjusted daily K. klt=101 (daily), fqt=2 (post-adjusted)."""
    code = to_efinance_a(ticker)
    raw = ef.stock.get_quote_history(
        stock_codes=code,
        beg=start.strftime("%Y%m%d"),
        end=end.strftime("%Y%m%d"),
        klt=101, fqt=2,
    )
    if raw is None or len(raw) == 0:
        return pd.DataFrame(columns=["ticker", "date", "open", "high", "low", "close", "volume"])

    df = pd.DataFrame({
        "ticker": ticker,
        "date":   pd.to_datetime(raw["日期"]).dt.date,
        "open":   raw["开盘"].astype(float),
        "high":   raw["最高"].astype(float),
        "low":    raw["最低"].astype(float),
        "close":  raw["收盘"].astype(float),
        "volume": raw["成交量"].astype("int64"),
    })
    return df[["ticker", "date", "open", "high", "low", "close", "volume"]]


def _save_prices(conn, df: pd.DataFrame) -> int:
    """INSERT ... ON DUPLICATE KEY UPDATE so rebases overwrite cleanly."""
    sql = """
        INSERT INTO prices (ticker, date, open, high, low, close, volume)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            open=VALUES(open), high=VALUES(high), low=VALUES(low),
            close=VALUES(close), volume=VALUES(volume)
    """
    rows = [
        (
            r.ticker, r.date,
            to_float(r.open), to_float(r.high),
            to_float(r.low), to_float(r.close),
            to_int(r.volume),
        )
        for r in df.itertuples(index=False)
    ]
    with conn.cursor() as cur:
        cur.executemany(sql, rows)
    conn.commit()
    return len(rows)
