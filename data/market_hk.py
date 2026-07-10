"""HK market module: adapts HSI ingest to Pipeline protocol."""

from __future__ import annotations

import logging
from typing import Optional
import yfinance as yf
import pandas as pd

from db import get_conn, get_index_tickers, get_latest_snapshot_tickers, query, execute
from data import index_updater_hk
from data import stock_updater_hk
from core.http_utils import to_float

log = logging.getLogger(__name__)

market_id = "hk"


def update_index() -> tuple[list[str], int, int]:
    prev = set(get_latest_snapshot_tickers("HSI"))

    index_updater_hk.update_hsi()

    curr = set(get_latest_snapshot_tickers("HSI"))
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


def rebase(tickers: Optional[list[str]] = None, years: Optional[int] = None) -> dict[str, str]:
    targets = tickers if tickers else list_active_tickers()
    return stock_updater_hk.update_prices_batch(targets, full_rebase=True, years=years)
