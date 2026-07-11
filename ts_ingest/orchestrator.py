"""一键全量 backfill。phase: lists → prices → derive → financial。"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

import pymysql.cursors

from core.db_client import get_conn
from ts_ingest import budget
from ts_ingest.client import get_client
from ts_ingest.backfill_lists import (
    backfill_stocks_a, backfill_stocks_hk, backfill_stocks_us,
    backfill_etf_basic, backfill_hk_connect, backfill_index_weight,
)
from ts_ingest.backfill_stock_dates import backfill_stock_dates
from ts_ingest.backfill_prices import backfill_market
from ts_ingest.derive_periodic import derive_all
from ts_ingest.backfill_financial import backfill_all as fin_backfill_all
from ts_ingest.backfill_valuation import backfill_all as val_backfill_all
from ts_ingest.backfill_shareholder_return import backfill_all as sr_backfill_all

log = logging.getLogger(__name__)

PRECHECK_APIS = [
    "stock_basic", "fund_basic", "hs_const", "hk_basic", "us_basic",
    "income_vip", "balancesheet_vip", "cashflow_vip", "fina_indicator_vip",
    "index_weight", "daily_basic", "dividend", "repurchase", "stk_holdertrade",
]


@dataclass
class ExitReport:
    phases: dict = field(default_factory=dict)
    failed_apis_at_precheck: list = field(default_factory=list)
    elapsed_sec: float = 0.0

    def render(self) -> str:
        lines = [f"=== Tushare backfill exit report (elapsed {self.elapsed_sec:.0f}s) ==="]
        if self.failed_apis_at_precheck:
            lines.append(f"PRECHECK FAILED for: {self.failed_apis_at_precheck}")
        for phase, data in self.phases.items():
            lines.append(f"  [{phase}] {data}")
        lines.append(f"  budget: {budget.report()}")
        return "\n".join(lines)


def _list_a_share_tickers() -> list[str]:
    with get_conn() as conn:
        with conn.cursor(pymysql.cursors.DictCursor) as cur:
            cur.execute(
                "SELECT ticker FROM stocks "
                "WHERE ticker LIKE '%%.SH' OR ticker LIKE '%%.SZ' OR ticker LIKE '%%.BJ' "
                "ORDER BY ticker"
            )
            return [r["ticker"] for r in cur.fetchall()]


def _list_hk_tickers() -> list[str]:
    with get_conn() as conn:
        with conn.cursor(pymysql.cursors.DictCursor) as cur:
            cur.execute("SELECT ticker FROM stocks WHERE ticker LIKE '%%.HK' ORDER BY ticker")
            return [r["ticker"] for r in cur.fetchall()]


def _list_us_tickers() -> list[str]:
    with get_conn() as conn:
        with conn.cursor(pymysql.cursors.DictCursor) as cur:
            cur.execute(
                "SELECT ticker FROM stocks "
                "WHERE ticker NOT LIKE '%%.SH' AND ticker NOT LIKE '%%.SZ' "
                "  AND ticker NOT LIKE '%%.BJ' AND ticker NOT LIKE '%%.HK' "
                "ORDER BY ticker"
            )
            return [r["ticker"] for r in cur.fetchall()]


def run_full_backfill(scope: str = "all", market: str = "all",
                      dry_run: bool = False, start: str | None = None) -> ExitReport:
    """scope ∈ {all, lists, prices, derive, financial}; market ∈ {all, cn, hk, us}.

    start: YYYYMMDD，显式指定起点重新回填历史。financial 默认已是
    TUSHARE_BACKFILL_START 全量拉取；valuation 默认从上次同步点增量续拉，
    传 start 才会强制往回填。
    """
    budget.reset()
    rep = ExitReport()
    t0 = time.monotonic()

    log.info("=== Phase 0: precheck ===")
    client = get_client()
    failed = budget.precheck(client, PRECHECK_APIS)
    rep.failed_apis_at_precheck = failed
    if failed:
        log.warning(f"precheck failed for: {failed}; continuing only with passing APIs")

    if dry_run:
        log.info("dry_run=True → skipping data phases")
        rep.elapsed_sec = time.monotonic() - t0
        return rep

    if scope in ("all", "lists"):
        log.info("=== Phase 1: lists ===")
        rep.phases["lists"] = {
            "stocks_a":   backfill_stocks_a(),
            "stocks_hk":  backfill_stocks_hk(),
            "stocks_us":  backfill_stocks_us(),
            "etf_basic":  backfill_etf_basic(),
            "hk_connect": backfill_hk_connect(),
            "stock_dates": backfill_stock_dates(),  # UPDATE，须在 stocks_a/hk/us 之后跑
        }
        # 指数成分（最近一个交易日）— 调用方提供 trade_date，简化为今天前 5 日
        # 留给手动调用 backfill_index_weight，避免猜交易日。

    if scope in ("all", "prices"):
        log.info("=== Phase 2: prices (CN only - HK/US use yfinance) ===")
        prices_rep = {}
        if market in ("all", "cn"):
            prices_rep["cn"] = backfill_market(_list_a_share_tickers(), market="cn")
        if market in ("all", "hk"):
            prices_rep["hk"] = "skipped - use existing yfinance daily"
        if market in ("all", "us"):
            prices_rep["us"] = "skipped - use existing yfinance daily"
        rep.phases["prices"] = prices_rep

    if scope in ("all", "derive"):
        log.info("=== Phase 3: derive (weekly/monthly) ===")
        all_tickers = _list_a_share_tickers() + _list_hk_tickers() + _list_us_tickers()
        rep.phases["derive"] = derive_all(all_tickers)

    if scope in ("all", "financial"):
        log.info("=== Phase 4: financial ===")
        rep.phases["financial"] = fin_backfill_all(start=start) if start else fin_backfill_all()

    if scope in ("all", "valuation"):
        log.info("=== Phase 5: valuation ===")
        rep.phases["valuation"] = val_backfill_all(start=start)

    if scope in ("all", "shareholder_return"):
        log.info("=== Phase 6: shareholder_return ===")
        rep.phases["shareholder_return"] = sr_backfill_all(start=start)

    rep.elapsed_sec = time.monotonic() - t0
    return rep
