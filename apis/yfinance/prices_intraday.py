"""US equity intraday prices via yfinance free tier (15m / 1h).

Thin entry: builds IntradaySpec and delegates to run_intraday_batch.
Writes prices_intraday; sync_log data_type intraday_15m / intraday_60m.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from apis.yfinance.prices_intraday_batch import (
    SUPPORTED_INTERVALS,
    build_intraday_spec,
    default_universe,
    run_intraday_batch,
    save_rows,
    sync_type,
)

# Backward-compatible private aliases for existing tests / callers.
_sync_type = sync_type
_save_rows = save_rows


def update_intraday(
    interval: str,
    full_rebase: bool = False,
    tickers: Optional[List[str]] = None,
) -> Dict[str, str]:
    """批量增量拉取美股 intraday，写入 prices_intraday。

    Args:
        interval: '15m' 或 '1h'
        full_rebase: True 时忽略 sync_log，从 floor_date 全量拉取
        tickers: 宇宙；None 时在 probe 成功后用 SP500∪R1000 默认宇宙
    Returns:
        {ticker: 'ok' | 'no_data' | 'error: <msg>'}
    """
    spec = build_intraday_spec(interval)
    return run_intraday_batch(tickers, spec=spec, full_rebase=full_rebase)


__all__ = [
    "SUPPORTED_INTERVALS",
    "update_intraday",
    "default_universe",
    "_sync_type",
    "_save_rows",
]
