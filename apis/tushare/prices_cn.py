"""A-share daily-K updater via Tushare (pre-adjusted, qfq).

Thin entry: builds CnPriceSpec and delegates to run_cn_equity_batch.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from apis.tushare.prices_cn_batch import CnPriceSpec, run_cn_equity_batch

SYNC_DATA_TYPE = "price"


def update_prices_batch(
    tickers: List[str], full_rebase: bool = False, years: Optional[int] = None
) -> Dict[str, str]:
    """批量增量拉取，参考US补缺逻辑。

    Args:
      tickers: canonical A-share tickers (e.g., 600519.SH)
      full_rebase: if True, ignore sync_log and pull from START_DATE_CN
      years: 指定历史年数（None 时使用 START_DATE_CN）

    Returns: {ticker: status}
    """
    spec = CnPriceSpec(
        label="cn",
        freq="D",
        data_type="price",
        price_table="prices",
        on_duplicate=True,
    )
    return run_cn_equity_batch(
        tickers, spec=spec, full_rebase=full_rebase, years=years
    )
