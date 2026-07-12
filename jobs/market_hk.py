"""HK market module: adapts HSI ingest to Pipeline protocol."""

from __future__ import annotations

import logging
from typing import Optional

from modules.db_admin import get_index_tickers
from apis.static import hsi_csv
from apis.yfinance import prices_hk as stock_updater_hk

log = logging.getLogger(__name__)

market_id = "hk"


def update_index() -> tuple[list[str], int, int]:
    prev = set(get_index_tickers("HSI"))

    hsi_csv.update_hsi()

    curr = set(get_index_tickers("HSI"))
    new_added = sorted(curr - prev)
    return new_added, len(curr), len(prev - curr)


def list_active_tickers(index: str | None = None) -> list[str]:
    """Return active tickers. ``index`` is ignored (CN/HK single-universe)."""
    return get_index_tickers("HSI")


def incremental(tickers: list[str]) -> dict[str, str]:
    """日线增量；新 ticker（无 sync_log）由 updater 自动全量回填。"""
    if not tickers:
        return {}
    return stock_updater_hk.update_prices_batch(tickers)


def update_index_price() -> int:
    """港股指数价暂不采集（yfinance 限速）；保留 Protocol 入口。"""
    return 0


def rebase(
    tickers: Optional[list[str]] = None,
    years: Optional[int] = None,
    index: str | None = None,
) -> dict[str, str]:
    """Full re-pull. ``index`` is ignored (HK single-universe)."""
    targets = tickers if tickers else list_active_tickers()
    return stock_updater_hk.update_prices_batch(targets, full_rebase=True, years=years)


def weekly(tickers: list[str] | None = None) -> dict[str, str]:
    """港股周线未实现；CLI 未开放 --market hk。"""
    raise NotImplementedError("HK weekly not supported")


def intraday(
    intervals: list[str] | None = None,
    full_rebase: bool = False,
) -> dict[str, str]:
    """HK 无分钟线；Protocol 统一入口，no-op。"""
    return {}
