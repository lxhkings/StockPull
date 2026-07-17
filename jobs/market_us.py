"""US market module: thin adapter exposing the MarketModule protocol.

Wraps apis.static SP500/Russell adapters and yfinance price updaters
into the Pipeline contract.

支持指数：
- SP500（S&P 500，约503支）
- RUSSELL1000（Russell 1000，约1008支）
- 默认组合：SP500 + RUSSELL1000（约1016支）
"""

from __future__ import annotations

import logging
from typing import Optional

from modules.db_admin import get_index_tickers
from apis.static import sp500_github
from apis.static import russell_ishares
from apis.yfinance import prices_us as stock_updater_us
from apis.yfinance.prices_index import update_index_prices

log = logging.getLogger(__name__)

market_id = "us"


def update_index() -> tuple[list[str], int, int]:
    """Run SP500 + Russell1000 snapshot + change detection.

    Returns:
        (new_added_tickers, total_inserted_rows, removed_count)
    """
    # SP500
    prev_sp500 = set(get_index_tickers("SP500"))
    sp500_github.update_sp500()
    curr_sp500 = set(get_index_tickers("SP500"))
    sp500_new = sorted(curr_sp500 - prev_sp500)
    sp500_removed = len(prev_sp500 - curr_sp500)

    # Russell 1000
    prev_r1k = set(get_index_tickers("RUSSELL1000"))
    russell_ishares.update_russell1000()
    curr_r1k = set(get_index_tickers("RUSSELL1000"))
    r1k_new = sorted(curr_r1k - prev_r1k)
    r1k_removed = len(prev_r1k - curr_r1k)

    # 合并新增
    all_new = sorted(set(sp500_new) | set(r1k_new))
    total_inserted = len(curr_sp500) + len(curr_r1k)
    total_removed = sp500_removed + r1k_removed

    return all_new, total_inserted, total_removed


def list_active_tickers(index: Optional[str] = None) -> list[str]:
    """返回美股 ticker 列表。

    Args:
        index: 指定指数（SP500/RUSSELL1000），None 返回组合（SP500+R1000）

    Returns:
        ticker 列表
    """
    if index == "SP500":
        return get_index_tickers("SP500")
    if index == "RUSSELL1000":
        return get_index_tickers("RUSSELL1000")

    # 默认：SP500 + Russell 1000 组合（约1016支）
    sp500 = get_index_tickers("SP500")
    r1k = get_index_tickers("RUSSELL1000")
    combined = sorted(set(sp500) | set(r1k))
    return combined


def incremental(tickers: list[str]) -> dict[str, str]:
    """日线增量；新 ticker（无 sync_log）由 updater 自动全量回填。"""
    if not tickers:
        return {}
    return stock_updater_us.update_prices_batch(tickers)


def update_index_price() -> int:
    """US 宽基 + 行业 ETF 日线 → index_prices（apis.yfinance.prices_index）。"""
    return update_index_prices()


def rebase(
    tickers: Optional[list[str]] = None,
    years: Optional[int] = None,
    index: Optional[str] = None,
) -> dict[str, str]:
    """US rebase: full re-pull from specified years (raw prices, no hfq)."""
    targets = tickers if tickers else list_active_tickers(index=index)
    return stock_updater_us.update_prices_batch(targets, full_rebase=True, years=years)


def weekly(tickers: list[str] | None = None) -> dict[str, str]:
    """Pull weekly prices for US universe into prices_weekly."""
    from apis.yfinance import prices_us_weekly as stock_updater_us_weekly
    targets = tickers or list_active_tickers()
    return stock_updater_us_weekly.update_weekly_batch(targets)


def intraday(
    intervals: list[str] | None = None,
    full_rebase: bool = False,
) -> dict[str, str]:
    """Pull intraday (15m / 1h) into prices_intraday.

    Default intervals = SUPPORTED_INTERVALS（与 CLI prices intraday 一致）。
    Universe = list_active_tickers()（与 daily/weekly 默认宇宙一致）。
    """
    from apis.yfinance.prices_intraday import update_intraday, SUPPORTED_INTERVALS
    tickers = list_active_tickers()
    result: dict[str, str] = {}
    for ivl in (intervals or SUPPORTED_INTERVALS):
        result.update(
            update_intraday(ivl, full_rebase=full_rebase, tickers=tickers)
        )
    return result
