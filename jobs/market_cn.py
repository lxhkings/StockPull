"""A-share market module: 全量 A 股 via tushare stock_basic + 行业 ETF 价."""

from __future__ import annotations

import logging
from typing import Optional

from core.db_client import get_conn, query
from apis.tushare import prices_cn as stock_updater_cn
from apis.tushare.backfill_lists import backfill_stocks_a

log = logging.getLogger(__name__)

market_id = "cn"


def update_index() -> tuple[list[str], int, int]:
    """更新全量A股列表（从tushare stock_basic）。"""
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM stocks "
            "WHERE ticker LIKE '%%.SH' OR ticker LIKE '%%.SZ' OR ticker LIKE '%%.BJ'"
        )
        prev_count = cur.fetchone()[0]
    finally:
        conn.close()

    inserted = backfill_stocks_a()

    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM stocks "
            "WHERE ticker LIKE '%%.SH' OR ticker LIKE '%%.SZ' OR ticker LIKE '%%.BJ'"
        )
        curr_count = cur.fetchone()[0]
    finally:
        conn.close()

    added = curr_count - prev_count
    log.info(f"[cn] stocks表更新: prev={prev_count}, curr={curr_count}, added={added}")
    # new_tickers返回空，因为list_active_tickers直接读stocks表
    return [], inserted, 0


def list_active_tickers(index: str | None = None) -> list[str]:
    """Return active tickers. ``index`` is ignored (CN full A-share universe)."""
    rows = query(
        "SELECT ticker FROM stocks "
        "WHERE ticker LIKE '%%.SH' OR ticker LIKE '%%.SZ' OR ticker LIKE '%%.BJ' "
        "ORDER BY ticker"
    )
    return [r["ticker"] for r in rows]


def backfill_new(new_tickers: list[str]) -> dict[str, str]:
    if not new_tickers:
        return {}
    return stock_updater_cn.update_prices_batch(new_tickers)


def incremental(tickers: list[str]) -> dict[str, str]:
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
