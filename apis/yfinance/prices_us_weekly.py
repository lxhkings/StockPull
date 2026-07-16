"""US equity weekly prices via yfinance (interval=1wk)."""
from __future__ import annotations

from datetime import datetime, timedelta, date
from typing import Dict, List

from apis.yfinance.probe import probe_weekly
from apis.yfinance.prices_batch import UsPriceSpec, run_us_equity_batch


def _last_us_weekly_date() -> date:
    """Return Monday of the most recently completed US trading week."""
    now = datetime.now()
    weekday = now.weekday()
    hour = now.hour
    today = now.date()
    this_monday = today - timedelta(days=weekday)
    if (weekday == 5 and hour >= 5) or weekday == 6:
        return this_monday
    return this_monday - timedelta(days=7)


def update_weekly_batch(tickers: List[str], full_rebase: bool = False) -> Dict[str, str]:
    def _end_exclusive(target: date) -> date:
        return target + timedelta(days=7)

    # Build Spec at call time so patches on this module's probe_weekly / _last_us_weekly_date apply.
    spec = UsPriceSpec(
        label="weekly batch",
        interval="1wk",
        data_type="price_weekly",
        price_table="prices_weekly",
        probe=probe_weekly,
        target_date=_last_us_weekly_date,
        end_exclusive=_end_exclusive,
        on_duplicate=False,
        support_years=False,
    )
    return run_us_equity_batch(tickers, spec=spec, full_rebase=full_rebase)
