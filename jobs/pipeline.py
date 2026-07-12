"""Generic per-market pipeline orchestrator.

A market module must expose MarketModule (see Protocol below).
CN/HK: list_active_tickers ignores index; intraday/weekly may no-op.
US: index filters SP500/RUSSELL1000; intraday is CLI-only (not in daily).

Price path: single incremental() — new tickers have empty sync_log so
updaters already full-history pull; no separate backfill_new step.
"""

from __future__ import annotations

import logging
from typing import Optional, Protocol

log = logging.getLogger(__name__)


class MarketModule(Protocol):
    market_id: str

    def update_index(self) -> tuple[list[str], int, int]: ...
    def list_active_tickers(self, index: str | None = None) -> list[str]: ...
    def incremental(self, tickers: list[str]) -> dict[str, str]: ...
    def update_index_price(self) -> int: ...
    def rebase(
        self,
        tickers: list[str] | None = None,
        years: int | None = None,
        index: str | None = None,
    ) -> dict[str, str]: ...
    def weekly(self, tickers: list[str] | None = None) -> dict[str, str]: ...
    def intraday(
        self,
        intervals: list[str] | None = None,
        full_rebase: bool = False,
    ) -> dict[str, str]: ...


class Pipeline:
    def __init__(self, market_module: MarketModule):
        self.m = market_module

    def daily(self, index: Optional[str] = None) -> None:
        mid = self.m.market_id
        log.info(f"[{mid}] === Step 1: update index constituents ===")
        new_tickers, inserted, removed = self.m.update_index()
        log.info(
            f"[{mid}] index: +{len(new_tickers)} new, "
            f"{inserted} rows in snapshot, -{removed} removed"
        )
        if new_tickers:
            log.info(
                f"[{mid}] {len(new_tickers)} new tickers will full-history via incremental "
                f"(empty sync_log)"
            )

        log.info(f"[{mid}] === Step 2: incremental prices ===")
        all_tickers = self.m.list_active_tickers(index=index)
        log.info(f"[{mid}] incremental: {len(all_tickers)} tickers")
        self.m.incremental(all_tickers)

        log.info(f"[{mid}] === Step 3: update index / ETF price ===")
        rows = self.m.update_index_price()
        log.info(f"[{mid}] index price: +{rows} rows")

        log.info(f"[{mid}] === pipeline complete ===")
