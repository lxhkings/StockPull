"""A-share market module: 全量 A 股 via tushare stock_basic + 行业 ETF 价."""

from __future__ import annotations

import logging
from typing import Optional

from core.db_client import query
from apis.tushare import prices_cn as stock_updater_cn
from apis.tushare.backfill_lists import backfill_stocks_a

log = logging.getLogger(__name__)

market_id = "cn"


def update_index() -> tuple[list[str], int, int]:
    """更新全量 A 股列表；返回 (added_tickers, backfill_inserted, removed_count)。

    added/removed 基于 stocks 表可见 A 股 ticker 集合前后差（非指数 constituent_changes）。
    新票全量仍依赖空 sync_log + incremental；本函数不单独 backfill 价格。
    """
    prev = set(list_active_tickers())
    inserted = backfill_stocks_a()
    curr = set(list_active_tickers())
    added = sorted(curr - prev)
    removed = len(prev - curr)
    log.info(
        f"[cn] stocks set diff: prev={len(prev)}, curr={len(curr)}, "
        f"+{len(added)} -{removed}, backfill_inserted={inserted}"
    )
    return added, inserted, removed


def list_active_tickers(index: str | None = None) -> list[str]:
    """Return active tickers. ``index`` is ignored (CN full A-share universe)."""
    rows = query(
        "SELECT ticker FROM stocks "
        "WHERE ticker LIKE '%%.SH' OR ticker LIKE '%%.SZ' OR ticker LIKE '%%.BJ' "
        "ORDER BY ticker"
    )
    return [r["ticker"] for r in rows]


def incremental(tickers: list[str]) -> dict[str, str]:
    """日线增量；新 ticker（无 sync_log）由 updater 自动全量回填。"""
    if not tickers:
        return {}
    return stock_updater_cn.update_prices_batch(tickers)


def update_index_price() -> int:
    """行业 ETF 后复权日线 → index_prices（index_id = ts_code）。无宽基指数价。"""
    from apis.tushare.etf_cn import update_etf_prices
    return update_etf_prices()


def rebase(
    tickers: Optional[list[str]] = None,
    years: Optional[int] = None,
    index: str | None = None,
) -> dict[str, str]:
    """Full re-pull from START_DATE_CN to fix qfq drift. ``index`` is ignored (CN full-universe)."""
    targets = tickers if tickers else list_active_tickers()
    return stock_updater_cn.update_prices_batch(targets, full_rebase=True, years=years)


def weekly(tickers: list[str] | None = None) -> dict[str, str]:
    """Pull weekly prices for CN universe into prices_weekly."""
    from apis.tushare import prices_cn_weekly
    targets = tickers or list_active_tickers()
    return prices_cn_weekly.update_weekly_batch(targets)


def intraday(
    intervals: list[str] | None = None,
    full_rebase: bool = False,
) -> dict[str, str]:
    """CN 无分钟线；Protocol 统一入口，no-op。"""
    return {}
