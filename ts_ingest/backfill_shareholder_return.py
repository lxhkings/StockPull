"""A 股股东回报（分红送股/股票回购/股东增减持）回填，tushare dividend/repurchase/stk_holdertrade 接口。"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

import pymysql.cursors

from config import TUSHARE_BACKFILL_START
from core.db_client import get_conn
from ts_ingest.client import get_client
from ts_ingest.transform_shareholder_return import (
    transform_dividend_rows,
    transform_repurchase_rows,
    transform_holdertrade_rows,
)

log = logging.getLogger(__name__)


def _list_a_share_tickers() -> list[str]:
    with get_conn() as conn:
        with conn.cursor(pymysql.cursors.DictCursor) as cur:
            cur.execute(
                "SELECT ticker FROM stocks "
                "WHERE ticker LIKE '%%.SH' OR ticker LIKE '%%.SZ' OR ticker LIKE '%%.BJ' "
                "ORDER BY ticker"
            )
            return [r["ticker"] for r in cur.fetchall()]


def backfill_dividend_one(ts_code: str) -> int:
    client = get_client()
    df = client.call("dividend", ts_code=ts_code)
    if df is None or df.empty:
        return 0
    rows = transform_dividend_rows(df)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO cn_dividend "
                "(ts_code, end_date, ann_date, div_proc, stk_div, stk_bo_rate, stk_co_rate, "
                " cash_div, cash_div_tax, record_date, ex_date, pay_date, div_listdate, "
                " imp_ann_date, base_date, base_share) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                "ON DUPLICATE KEY UPDATE "
                "  div_proc=VALUES(div_proc), stk_div=VALUES(stk_div), "
                "  stk_bo_rate=VALUES(stk_bo_rate), stk_co_rate=VALUES(stk_co_rate), "
                "  cash_div=VALUES(cash_div), cash_div_tax=VALUES(cash_div_tax), "
                "  record_date=VALUES(record_date), ex_date=VALUES(ex_date), "
                "  pay_date=VALUES(pay_date), div_listdate=VALUES(div_listdate), "
                "  imp_ann_date=VALUES(imp_ann_date), base_date=VALUES(base_date), "
                "  base_share=VALUES(base_share)",
                rows,
            )
        conn.commit()
    log.info(f"dividend@{ts_code}: {len(rows)} rows")
    return len(rows)


def backfill_dividend() -> dict:
    tickers = _list_a_share_tickers()
    total = 0
    for t in tickers:
        try:
            total += backfill_dividend_one(t)
        except Exception as e:
            log.error(f"dividend@{t}: {e}")
    log.info(f"dividend: {len(tickers)} tickers, {total} rows")
    return {"rows": total, "tickers": len(tickers)}
