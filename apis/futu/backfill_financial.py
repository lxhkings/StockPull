"""美股财务报表 backfill（利润/资产负债/现金流/关键指标）。

statement_type: 1=利润表 2=资产负债表 3=现金流量表 4=关键指标。
一个通用函数 backfill_statement 处理 4 种 statement_type → 4 张表。
节流由 ticker_stream 统一处理。
"""
from __future__ import annotations

import json
import logging

from config import FUTU_FINANCIAL_TYPE, FUTU_CURRENCY_CODE
from core.db_client import get_conn
from apis.futu.client import clean_date, get_client, to_futu_code
from apis.futu.concurrency import ticker_stream

log = logging.getLogger(__name__)

# (statement_type, target_table)
STATEMENT_TABLES = [
    (1, "us_fin_income"),
    (2, "us_fin_balance"),
    (3, "us_fin_cashflow"),
    (4, "us_fin_indicator"),
]

PAGE_NUM = 50


def _report_to_row(ticker: str, rpt: dict) -> tuple:
    return (
        ticker,
        clean_date(rpt.get("date_time_str")),       # period_end
        str(rpt.get("financial_type") or ""),
        str(rpt.get("fiscal_year") or ""),
        rpt.get("period_text"),
        rpt.get("currency_code"),
        rpt.get("accounting_standards"),
        json.dumps(rpt, ensure_ascii=False, default=str),
    )


def backfill_statement(
    client, ticker: str, statement_type: int, table: str,
) -> tuple[int, str | None]:
    """抓单只单表全历史（分页），upsert。返回 (写入行数, 最新 period_end)。"""
    code = to_futu_code(ticker)
    rows: list[tuple] = []
    latest_period: str | None = None
    next_key = None
    while True:
        data = client.call(
            "get_financials_statements", code,
            statement_type=statement_type,
            financial_type=FUTU_FINANCIAL_TYPE,
            currency_code=FUTU_CURRENCY_CODE,
            next_key=next_key, num=PAGE_NUM,
        )
        report_list = (data or {}).get("report_list", []) if isinstance(data, dict) else []
        for rpt in report_list:
            period = clean_date(rpt.get("date_time_str"))
            if not period:
                continue
            if latest_period is None or period > latest_period:
                latest_period = period
            rows.append(_report_to_row(ticker, rpt))
        next_key = (data or {}).get("next_key", "-1") if isinstance(data, dict) else "-1"
        if not report_list or next_key == "-1":
            break

    if not rows:
        return 0, latest_period
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.executemany(
                f"INSERT INTO {table} "
                "(ticker, period_end, financial_type, fiscal_year, period_text, "
                " currency_code, accounting_standards, raw_payload) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s) "
                "ON DUPLICATE KEY UPDATE "
                "  fiscal_year=VALUES(fiscal_year), period_text=VALUES(period_text), "
                "  currency_code=VALUES(currency_code), "
                "  accounting_standards=VALUES(accounting_standards), "
                "  raw_payload=VALUES(raw_payload)",
                rows,
            )
        conn.commit()
    log.info(f"{table} {ticker}: {len(rows)} rows")
    return len(rows), latest_period


def fin_sync_one(client, ticker: str) -> int:
    """同步单只 ticker 的 4 张财务表全历史。返回总写入行数。"""
    total = 0
    for st, table in STATEMENT_TABLES:
        rows_added, _ = backfill_statement(client, ticker, st, table)
        total += rows_added
    return total


def backfill_all(tickers: list[str], force: bool = False) -> dict:
    client = get_client()
    rows, ok, skipped = ticker_stream(fin_sync_one, client, tickers, "us_financial", force=force)
    return {"rows": rows, "tickers": ok, "skipped": skipped}
