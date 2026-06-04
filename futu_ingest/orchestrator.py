"""美股基本面 backfill 编排。scope ∈ {all, financial, earnings, actions, profile, revenue, shareholders, efficiency}。"""
from __future__ import annotations

import logging
import time

import pymysql.cursors

from db import get_conn
from futu_ingest.backfill_financial import backfill_all as fin_backfill_all
from futu_ingest.backfill_earnings import backfill_all as earnings_backfill_all
from futu_ingest.backfill_actions import backfill_all as actions_backfill_all
from futu_ingest.backfill_profile import backfill_all as profile_backfill_all
from futu_ingest.backfill_revenue import backfill_all as revenue_backfill_all
from futu_ingest.backfill_shareholders import backfill_all as shareholders_backfill_all
from futu_ingest.backfill_efficiency import backfill_all as efficiency_backfill_all
from futu_ingest.snapshot_daily import run_daily as snapshot_run_daily
from futu_ingest.snapshot_daily_ext import run_daily_ext as daily_ext_run
from futu_ingest.snapshot_weekly import run_weekly as snapshot_run_weekly

log = logging.getLogger(__name__)


def list_us_tickers() -> list[str]:
    """stocks 表中有日线价格数据的美股 ticker（非 CN/HK）。"""
    with get_conn() as conn:
        with conn.cursor(pymysql.cursors.DictCursor) as cur:
            cur.execute(
                "SELECT DISTINCT s.ticker FROM stocks s "
                "INNER JOIN prices p ON s.ticker = p.ticker "
                "WHERE s.ticker NOT LIKE '%%.SH' AND s.ticker NOT LIKE '%%.SZ' "
                "  AND s.ticker NOT LIKE '%%.BJ' AND s.ticker NOT LIKE '%%.HK' "
                "ORDER BY s.ticker"
            )
            return [r["ticker"] for r in cur.fetchall()]


def run_sync(scope: str = "all", force: bool = False) -> dict:
    """统一采集编排。scope 选接口组；force=True 忽略节流全量。

    scope ∈ {all, other, daily, weekly, financial, earnings, actions,
             profile, revenue, shareholders, efficiency}。
    "other" = 除 financial 外的全部。
    """
    t0 = time.monotonic()
    tickers = list_us_tickers()
    log.info(f"futu sync scope={scope} force={force}, {len(tickers)} US tickers")
    rep: dict = {"scope": scope, "force": force, "tickers": len(tickers)}

    def want(s: str) -> bool:
        if scope == "other":
            return s != "financial"  # 排除 financial
        return scope in ("all", s)

    if want("financial"):
        log.info("=== financial ===")
        rep["financial"] = fin_backfill_all(tickers, force=force)
    if want("earnings"):
        log.info("=== earnings (+ PIT) ===")
        rep["earnings"] = earnings_backfill_all(tickers, force=force)
    if want("actions"):
        log.info("=== actions ===")
        rep["actions"] = actions_backfill_all(tickers, force=force)
    if want("profile"):
        log.info("=== profile ===")
        rep["profile"] = profile_backfill_all(tickers, force=force)
    if want("revenue"):
        log.info("=== revenue ===")
        rep["revenue"] = revenue_backfill_all(tickers, force=force)
    if want("shareholders"):
        log.info("=== shareholders ===")
        rep["shareholders"] = shareholders_backfill_all(tickers, force=force)
    if want("efficiency"):
        log.info("=== efficiency ===")
        rep["efficiency"] = efficiency_backfill_all(tickers, force=force)
    if want("daily"):
        log.info("=== daily snapshot ===")
        rep["daily"] = snapshot_run_daily(tickers, force=force)
        rep["daily_ext"] = daily_ext_run(tickers, force=force)
    if want("weekly"):
        log.info("=== weekly snapshot ===")
        rep["weekly"] = snapshot_run_weekly(tickers, force=force)

    rep["elapsed_sec"] = round(time.monotonic() - t0, 1)
    return rep
