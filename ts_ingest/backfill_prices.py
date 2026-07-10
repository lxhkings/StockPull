"""三市场日 K backfill（A/HK 用 qfq 前复权；US 不复权）。"""
from __future__ import annotations

import logging
import time
from datetime import date

import pandas as pd

from config import TUSHARE_BACKFILL_START
from data.base import to_float, to_int
from db import get_conn, set_sync_error, set_sync_ok
from core.progress import log_progress
from ts_ingest.client import get_client

log = logging.getLogger(__name__)

SYNC_DATA_TYPE = "price"


def _normalize_pro_bar(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    out = pd.DataFrame({
        "date": pd.to_datetime(df["trade_date"], format="%Y%m%d").dt.date,
        "open": df["open"].apply(to_float),
        "high": df["high"].apply(to_float),
        "low":  df["low"].apply(to_float),
        "close": df["close"].apply(to_float),
        "volume": df["vol"].apply(to_int),
    })
    return out.sort_values("date").reset_index(drop=True)


def _pro_bar_kwargs(ticker: str, market: str, start: str) -> dict:
    if market == "cn":
        return {"ts_code": ticker, "adj": "qfq", "start_date": start, "freq": "D"}
    if market == "hk":
        return {"ts_code": ticker, "adj": "qfq", "asset": "HK", "start_date": start, "freq": "D"}
    if market == "us":
        return {"ts_code": ticker, "asset": "US", "start_date": start, "freq": "D"}
    raise ValueError(market)


def backfill_one(ticker: str, market: str, start: str = TUSHARE_BACKFILL_START) -> int:
    client = get_client()
    df_raw = client.pro_bar(**_pro_bar_kwargs(ticker, market, start))
    df = _normalize_pro_bar(df_raw)
    if df.empty:
        log.warning(f"{ticker}: no bars returned")
        return 0
    rows = [
        (ticker, r["date"], r["open"], r["high"], r["low"], r["close"], r["volume"])
        for _, r in df.iterrows()
    ]
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO prices (ticker, date, open, high, low, close, volume) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s) "
                "ON DUPLICATE KEY UPDATE "
                "  open=VALUES(open), high=VALUES(high), low=VALUES(low), "
                "  close=VALUES(close), volume=VALUES(volume)",
                rows,
            )
        conn.commit()
        last_date = max(r[1] for r in rows)
        set_sync_ok(conn, ticker, SYNC_DATA_TYPE, last_date, len(rows))
    return len(rows)


def backfill_market(tickers: list[str], market: str,
                    start: str = TUSHARE_BACKFILL_START) -> dict:
    """全 ticker 顺序 backfill；失败计入 sync_log error 并继续。"""
    ok = 0
    failed: list[str] = []
    t0 = time.monotonic()
    for i, t in enumerate(tickers, 1):
        try:
            backfill_one(t, market=market, start=start)
            ok += 1
        except Exception as e:
            failed.append(t)
            log.error(f"[{market}] {t} backfill failed: {e}")
            try:
                with get_conn() as conn:
                    set_sync_error(conn, t, SYNC_DATA_TYPE, str(e))
            except Exception:
                pass
        log_progress(i, len(tickers), t0, every=100, context=f"[{market}] ",
                     extra=f"ok={ok}, failed={len(failed)}")
    return {"ok": ok, "failed": failed, "total": len(tickers)}
