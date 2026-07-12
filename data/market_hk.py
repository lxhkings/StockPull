"""HK market module: adapts HSI ingest to Pipeline protocol."""

from __future__ import annotations

import logging
from typing import Optional

from core.db_client import get_conn, query
from modules.db_admin import get_index_tickers
from data import index_updater_hk
from apis.yfinance import prices_hk as stock_updater_hk

log = logging.getLogger(__name__)

market_id = "hk"


def update_index() -> tuple[list[str], int, int]:
    prev = set(get_index_tickers("HSI"))

    index_updater_hk.update_hsi()

    curr = set(get_index_tickers("HSI"))
    new_added = sorted(curr - prev)
    return new_added, len(curr), len(prev - curr)


def list_active_tickers(index: str | None = None) -> list[str]:
    """Return active tickers. ``index`` is ignored (CN/HK single-universe)."""
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


def rebase(
    tickers: Optional[list[str]] = None,
    years: Optional[int] = None,
    index: str | None = None,
) -> dict[str, str]:
    """Full re-pull. ``index`` is ignored (HK single-universe)."""
    targets = tickers if tickers else list_active_tickers()
    return stock_updater_hk.update_prices_batch(targets, full_rebase=True, years=years)
