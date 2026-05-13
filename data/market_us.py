"""US market module: thin adapter exposing the MarketModule protocol.

Wraps existing index_updater_us.update_sp500() and stock_updater_us.update_prices_batch()
into the Pipeline contract.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Optional

import yfinance as yf

from db import get_conn, get_index_tickers, get_latest_snapshot_tickers, query, execute
from data import index_updater_us
from data import stock_updater_us
from data.base import to_float

log = logging.getLogger(__name__)

market_id = "us"


def update_index() -> tuple[list[str], int, int]:
    """Run SP500 snapshot + change detection. Returns (new_added_tickers, inserted, removed)."""
    prev_tickers = set(get_latest_snapshot_tickers("SP500"))

    index_updater_us.update_sp500()

    curr_tickers = set(get_latest_snapshot_tickers("SP500"))

    new_added = sorted(curr_tickers - prev_tickers)
    removed = len(prev_tickers - curr_tickers)
    return new_added, len(curr_tickers), removed


def list_active_tickers() -> list[str]:
    return get_index_tickers("SP500")


def backfill_new(new_tickers: list[str]) -> dict[str, str]:
    """Backfill = full HISTORY_YEARS_US pull. Same code path as incremental
    because sync_log will be empty for these tickers."""
    if not new_tickers:
        return {}
    return stock_updater_us.update_prices_batch(new_tickers)


def incremental(tickers: list[str]) -> dict[str, str]:
    if not tickers:
        return {}
    return stock_updater_us.update_prices_batch(tickers)


def update_index_price() -> int:
    """Pull ^GSPC daily close from yfinance, write to index_prices."""
    last = query(
        "SELECT MAX(date) AS d FROM index_prices WHERE index_id=%s", ("SP500",)
    )
    last_date = last[0]["d"] if last and last[0]["d"] else None

    start = last_date.isoformat() if last_date else "2010-01-01"
    df = yf.download("^GSPC", start=start, interval="1d",
                     auto_adjust=False, actions=False, progress=False)
    if df.empty:
        return 0

    df = df.reset_index()
    df.columns = [str(c).lower() if not isinstance(c, tuple) else str(c[0]).lower() for c in df.columns]
    rows = []
    for _, r in df.iterrows():
        d = r["date"].date() if hasattr(r["date"], "date") else r["date"]
        if last_date and d <= last_date:
            continue
        rows.append((d, "SP500", to_float(r.get("close"))))

    if not rows:
        return 0

    return execute(
        "INSERT IGNORE INTO index_prices (date, index_id, close) VALUES (%s,%s,%s)",
        rows, many=True
    )


def rebase(tickers: Optional[list[str]] = None) -> dict[str, str]:
    """US rebase is identical to incremental from the user's perspective:
    yfinance auto_adjust=False stores raw, and prior US data does not need hfq rebase."""
    raise NotImplementedError("US rebase not supported (raw prices, no hfq drift). "
                              "Use `daily` to refresh recent data.")
