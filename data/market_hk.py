"""HK market module: adapts HSI ingest to Pipeline protocol."""

from __future__ import annotations

import logging
from typing import Optional
import yfinance as yf
import pandas as pd

from db import get_conn, get_index_tickers, query, execute
from data import index_updater_hk
from data import stock_updater_hk
from data.base import to_float

log = logging.getLogger(__name__)

market_id = "hk"


def update_index() -> tuple[list[str], int, int]:
    conn = get_conn()
    try:
        prev = set(_latest_snapshot_tickers(conn, "HSI"))
    finally:
        conn.close()

    index_updater_hk.update_hsi()

    conn = get_conn()
    try:
        curr = set(_latest_snapshot_tickers(conn, "HSI"))
    finally:
        conn.close()
    new_added = sorted(curr - prev)
    return new_added, len(curr), len(prev - curr)


def list_active_tickers() -> list[str]:
    return get_index_tickers("HSI")


def backfill_new(new_tickers: list[str]) -> dict[str, str]:
    if not new_tickers:
        return {}
    return stock_updater_hk.update_prices_batch(new_tickers)


def incremental(tickers: list[str]) -> dict[str, str]:
    if not tickers:
        return {}
    return stock_updater_hk.update_prices_batch(tickers)


def update_index_price() -> int:
    # Skip due to yfinance rate limit. Run manually later.
    return 0


def rebase(tickers: Optional[list[str]] = None) -> dict[str, str]:
    targets = tickers if tickers else list_active_tickers()
    return stock_updater_hk.update_prices_batch(targets, full_rebase=True)


def _latest_snapshot_tickers(conn, index_id: str) -> list[str]:
    rows = query(
        """SELECT DISTINCT ticker FROM index_constituents
           WHERE index_id=%s AND snapshot_date = (
             SELECT MAX(snapshot_date) FROM index_constituents WHERE index_id=%s
           )""",
        (index_id, index_id)
    )
    return [r["ticker"] for r in rows]
