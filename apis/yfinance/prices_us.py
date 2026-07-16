"""US equity daily prices via yfinance (incremental by sync_log)."""
from __future__ import annotations

from datetime import timedelta
from typing import Dict, List, Optional

from core.trading_calendar import last_us_trading_date
from apis.yfinance.probe import probe_daily
from apis.yfinance.prices_batch import UsPriceSpec, run_us_equity_batch


def update_prices_batch(
    tickers: List[str], full_rebase: bool = False, years: Optional[int] = None
) -> Dict[str, str]:
    def _end_exclusive(target):
        return target + timedelta(days=1)

    spec = UsPriceSpec(
        label="batch",
        interval="1d",
        data_type="price",
        price_table="prices",
        probe=probe_daily,
        target_date=last_us_trading_date,
        end_exclusive=_end_exclusive,
        on_duplicate=False,
        support_years=True,
    )
    return run_us_equity_batch(
        tickers, spec=spec, full_rebase=full_rebase, years=years
    )
