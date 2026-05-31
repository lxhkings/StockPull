"""美股基本面 backfill 编排。scope ∈ {all, financial, earnings, actions}。"""
from __future__ import annotations

import logging
import time

import pymysql.cursors

from db import get_conn
from futu_ingest.backfill_financial import backfill_all as fin_backfill_all
from futu_ingest.backfill_earnings import backfill_all as earnings_backfill_all
from futu_ingest.backfill_actions import backfill_all as actions_backfill_all
from futu_ingest.snapshot_daily import run_daily as snapshot_run_daily

log = logging.getLogger(__name__)


def list_us_tickers() -> list[str]:
    """stocks 表中所有美股 ticker（非 CN/HK）。"""
    with get_conn() as conn:
        with conn.cursor(pymysql.cursors.DictCursor) as cur:
            cur.execute(
                "SELECT ticker FROM stocks "
                "WHERE ticker NOT LIKE '%%.SH' AND ticker NOT LIKE '%%.SZ' "
                "  AND ticker NOT LIKE '%%.BJ' AND ticker NOT LIKE '%%.HK' "
                "ORDER BY ticker"
            )
            return [r["ticker"] for r in cur.fetchall()]


def run_backfill(scope: str = "all") -> dict:
    """全量 backfill。scope: all/financial/earnings/actions。"""
    t0 = time.monotonic()
    tickers = list_us_tickers()
    log.info(f"futu backfill scope={scope}, {len(tickers)} US tickers")
    rep: dict = {"scope": scope, "tickers": len(tickers)}

    if scope in ("all", "financial"):
        log.info("=== phase: financial ===")
        rep["financial"] = fin_backfill_all(tickers)
    if scope in ("all", "earnings"):
        log.info("=== phase: earnings (+ PIT backfill) ===")
        rep["earnings"] = earnings_backfill_all(tickers)
    if scope in ("all", "actions"):
        log.info("=== phase: actions ===")
        rep["actions"] = actions_backfill_all(tickers)

    rep["elapsed_sec"] = round(time.monotonic() - t0, 1)
    return rep


def run_daily() -> dict:
    """每日增量：流通股 + 分析师快照。"""
    tickers = list_us_tickers()
    return snapshot_run_daily(tickers)
