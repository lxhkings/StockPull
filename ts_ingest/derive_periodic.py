"""从 prices 表派生 prices_weekly / prices_monthly。"""
from __future__ import annotations

import logging
import time

import pandas as pd
import pymysql.cursors

from db import get_conn
from core.progress import log_progress

log = logging.getLogger(__name__)


def _read_daily(ticker: str) -> pd.DataFrame:
    with get_conn() as conn:
        with conn.cursor(pymysql.cursors.DictCursor) as cur:
            cur.execute(
                "SELECT date, open, high, low, close, volume "
                "FROM prices WHERE ticker=%s ORDER BY date",
                (ticker,),
            )
            return pd.DataFrame(cur.fetchall())


def resample_ohlcv(daily: pd.DataFrame, freq: str) -> pd.DataFrame:
    if daily.empty:
        return pd.DataFrame()
    df = daily.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date")
    out = df.resample(freq).agg({
        "open":   "first",
        "high":   "max",
        "low":    "min",
        "close":  "last",
        "volume": "sum",
    }).dropna(subset=["close"])
    out = out.reset_index()
    out["date"] = out["date"].dt.date
    return out


def _write_periodic(table: str, ticker: str, df: pd.DataFrame) -> int:
    if df.empty:
        return 0
    rows = [
        (ticker, r["date"], float(r["open"]), float(r["high"]),
         float(r["low"]), float(r["close"]), int(r["volume"]))
        for _, r in df.iterrows()
    ]
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.executemany(
                f"INSERT INTO {table} (ticker, date, open, high, low, close, volume) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s) "
                "ON DUPLICATE KEY UPDATE "
                "  open=VALUES(open), high=VALUES(high), low=VALUES(low), "
                "  close=VALUES(close), volume=VALUES(volume)",
                rows,
            )
        conn.commit()
    return len(rows)


def derive_for_ticker(ticker: str) -> dict[str, int]:
    daily = _read_daily(ticker)
    weekly = resample_ohlcv(daily, "W-FRI")
    monthly = resample_ohlcv(daily, "ME")  # pandas 2.x: month-end
    n_w = _write_periodic("prices_weekly", ticker, weekly)
    n_m = _write_periodic("prices_monthly", ticker, monthly)
    return {"weekly": n_w, "monthly": n_m}


def derive_all(tickers: list[str]) -> dict:
    total_w = total_m = 0
    t0 = time.monotonic()
    for i, t in enumerate(tickers, 1):
        try:
            res = derive_for_ticker(t)
            total_w += res["weekly"]
            total_m += res["monthly"]
        except Exception as e:
            log.error(f"derive {t}: {e}")
        log_progress(i, len(tickers), t0, every=500,
                     context="derive ", extra=f"weekly={total_w} monthly={total_m}")
    return {"weekly_rows": total_w, "monthly_rows": total_m}
