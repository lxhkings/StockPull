"""Generic per-market pipeline orchestrator.

A market module must expose:
  market_id: str
  update_index() -> tuple[list[str], int, int]
      (new_tickers_added_today, total_inserted, removed_count)
  list_active_tickers(index: str | None = None) -> list[str]
      All tickers currently in this market's universe.
      US uses ``index`` for SP500/RUSSELL1000; CN/HK ignore it.
  backfill_new(new_tickers: list[str]) -> dict[str, str]
      Pull full history for newly added tickers. Returns per-ticker status.
  incremental(tickers: list[str]) -> dict[str, str]
      Resume-from-sync_log for existing tickers.
  update_index_price() -> int
      Update the index's own daily close. Returns rows inserted.
  rebase(tickers: list[str] | None = None) -> dict[str, str]
      Full re-pull from START_DATE for qfq rebase. Optional to implement
      (US module raises NotImplementedError).
"""

from __future__ import annotations

import logging
from typing import Optional, Protocol

log = logging.getLogger(__name__)


class MarketModule(Protocol):
    market_id: str
    def update_index(self) -> tuple[list[str], int, int]: ...
    def list_active_tickers(self, index: str | None = None) -> list[str]: ...
    def backfill_new(self, new_tickers: list[str]) -> dict[str, str]: ...
    def incremental(self, tickers: list[str]) -> dict[str, str]: ...
    def update_index_price(self) -> int: ...


class Pipeline:
    def __init__(self, market_module: MarketModule):
        self.m = market_module

    def daily(self, index: Optional[str] = None) -> None:
        mid = self.m.market_id
        log.info(f"[{mid}] === Step 1: update index constituents ===")
        new_tickers, inserted, removed = self.m.update_index()
        log.info(f"[{mid}] index: +{len(new_tickers)} new, {inserted} rows in snapshot, -{removed} removed")

        if new_tickers:
            log.info(f"[{mid}] === Step 2: backfill {len(new_tickers)} new tickers ===")
            self.m.backfill_new(new_tickers)

        log.info(f"[{mid}] === Step 3: incremental update ===")
        all_tickers = self.m.list_active_tickers(index=index)
        log.info(f"[{mid}] incremental: {len(all_tickers)} tickers")
        self.m.incremental(all_tickers)

        log.info(f"[{mid}] === Step 4: update index price ===")
        rows = self.m.update_index_price()
        log.info(f"[{mid}] index price: +{rows} rows")

        if hasattr(self.m, "intraday"):
            log.info(f"[{mid}] === Step 5: intraday update ===")
            self.m.intraday()

        log.info(f"[{mid}] === pipeline complete ===")
