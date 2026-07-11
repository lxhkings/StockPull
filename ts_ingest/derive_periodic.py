"""从 prices 表派生 prices_weekly / prices_monthly。"""
from __future__ import annotations

import logging

import pandas as pd
import pymysql.cursors
from tqdm import tqdm

from core.db_client import get_conn
from ts_ingest.transform_periodic import resample_ohlcv, periodic_rows

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


def _write_periodic(table: str, ticker: str, df: pd.DataFrame) -> int:
    rows = periodic_rows(ticker, df)
    if not rows:
        return 0
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
    pbar = tqdm(tickers, desc="derive", unit="ticker")
    for t in pbar:
        try:
            res = derive_for_ticker(t)
            total_w += res["weekly"]
            total_m += res["monthly"]
        except Exception as e:
            log.error(f"derive {t}: {e}")
        pbar.set_postfix(weekly=total_w, monthly=total_m)
    return {"weekly_rows": total_w, "monthly_rows": total_m}
