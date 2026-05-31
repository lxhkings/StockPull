"""美股财务报表 backfill（利润/资产负债/现金流/关键指标）。

statement_type: 1=利润表 2=资产负债表 3=现金流量表 4=关键指标。
一个通用函数 backfill_statement 处理 4 种 statement_type → 4 张表。
"""
from __future__ import annotations

import json
import logging

from config import FUTU_FINANCIAL_TYPE, FUTU_CURRENCY_CODE
from db import get_conn
from futu_ingest.client import get_client, to_futu_code

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
        rpt.get("date_time_str"),       # period_end
        str(rpt.get("financial_type") or ""),
        str(rpt.get("fiscal_year") or ""),
        rpt.get("period_text"),
        rpt.get("currency_code"),
        rpt.get("accounting_standards"),
        json.dumps(rpt, ensure_ascii=False, default=str),
    )


def backfill_statement(client, ticker: str, statement_type: int, table: str) -> int:
    """抓单只单表全历史（分页），upsert。返回写入行数。"""
    code = to_futu_code(ticker)
    rows: list[tuple] = []
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
            if rpt.get("date_time_str"):
                rows.append(_report_to_row(ticker, rpt))
        next_key = (data or {}).get("next_key", "-1") if isinstance(data, dict) else "-1"
        if not report_list or next_key == "-1":
            break

    if not rows:
        return 0
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
    return len(rows)


def backfill_all(tickers: list[str]) -> dict:
    client = get_client()
    total = 0
    for t in tickers:
        for st, table in STATEMENT_TABLES:
            try:
                total += backfill_statement(client, t, st, table)
            except Exception as e:  # noqa: BLE001
                log.error(f"{table} {t}: {e}")
    return {"rows": total, "tickers": len(tickers)}
