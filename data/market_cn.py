"""A-share market module: adapts CN ingest to Pipeline protocol."""

from __future__ import annotations

import logging
from datetime import date
from typing import Optional

import akshare as ak
import pandas as pd

from db import get_conn, get_index_tickers, query, execute
from data import index_updater_cn
from data import stock_updater_cn
from data.base import to_float

log = logging.getLogger(__name__)

market_id = "cn"


def update_index() -> tuple[list[str], int, int]:
    conn = get_conn()
    try:
        prev = set(_latest_snapshot_tickers(conn, "CSI800"))
    finally:
        conn.close()

    index_updater_cn.update_csi800()

    conn = get_conn()
    try:
        curr = set(_latest_snapshot_tickers(conn, "CSI800"))
    finally:
        conn.close()
    new_added = sorted(curr - prev)
    return new_added, len(curr), len(prev - curr)


def list_active_tickers() -> list[str]:
    return get_index_tickers("CSI800")


def backfill_new(new_tickers: list[str]) -> dict[str, str]:
    if not new_tickers:
        return {}
    return stock_updater_cn.update_prices_batch(new_tickers)


def incremental(tickers: list[str]) -> dict[str, str]:
    if not tickers:
        return {}
    return stock_updater_cn.update_prices_batch(tickers)


def update_index_price() -> int:
    """中证800 指数 close via akshare (sh000906)."""
    last = query(
        "SELECT MAX(date) AS d FROM index_prices WHERE index_id=%s", ("CSI800",)
    )
    last_date = last[0]["d"] if last and last[0]["d"] else None

    raw = ak.stock_zh_index_daily(symbol="sh000906")
    if raw is None or raw.empty:
        return 0

    df = pd.DataFrame({
        "date":  pd.to_datetime(raw["date"]).dt.date,
        "close": raw["close"].astype(float),
    })
    if last_date:
        df = df[df["date"] > last_date]

    if df.empty:
        return 0

    rows = [(r.date, "CSI800", to_float(r.close)) for r in df.itertuples(index=False)]
    return execute(
        "INSERT IGNORE INTO index_prices (date, index_id, close) VALUES (%s,%s,%s)",
        rows, many=True,
    )


def rebase(tickers: Optional[list[str]] = None) -> dict[str, str]:
    """Full re-pull from START_DATE_CN to fix hfq drift."""
    targets = tickers if tickers else list_active_tickers()
    return stock_updater_cn.update_prices_batch(targets, full_rebase=True)


def _latest_snapshot_tickers(conn, index_id: str) -> list[str]:
    rows = query(
        """SELECT DISTINCT ticker FROM index_constituents
           WHERE index_id=%s AND snapshot_date = (
             SELECT MAX(snapshot_date) FROM index_constituents WHERE index_id=%s
           )""",
        (index_id, index_id)
    )
    return [r["ticker"] for r in rows]
