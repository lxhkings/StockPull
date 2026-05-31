"""美股财务报表 backfill（利润/资产负债/现金流/关键指标）。

statement_type: 1=利润表 2=资产负债表 3=现金流量表 4=关键指标。
一个通用函数 backfill_statement 处理 4 种 statement_type → 4 张表。

增量逻辑：
  - 首次（sync_log 无记录）：全量拉取，写 sync_log
  - 后续：全量拉取但只写入近 RECENT_YEARS 年数据（覆盖财报修正），跳过无新数据的 ticker
"""
from __future__ import annotations

import json
import logging
from datetime import date, timedelta

from config import FUTU_FINANCIAL_TYPE, FUTU_CURRENCY_CODE
from db import get_conn, get_last_sync, set_sync_ok, set_sync_error
from futu_ingest.client import get_client, to_futu_code

log = logging.getLogger(__name__)

SYNC_DATA_TYPE = "us_financial"
RECENT_YEARS = 2  # 增量模式下只写入近 N 年（覆盖财报修正）

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


def backfill_statement(
    client, ticker: str, statement_type: int, table: str,
    cutoff_date: str | None = None,
) -> tuple[int, str | None]:
    """抓单只单表全历史（分页），upsert。返回 (写入行数, 最新 period_end)。

    Args:
        cutoff_date: 若指定，只写入 period_end >= cutoff_date 的行（增量模式）。
    """
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
            period = rpt.get("date_time_str")
            if not period:
                continue
            if latest_period is None or period > latest_period:
                latest_period = period
            if cutoff_date and period < cutoff_date:
                continue
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


def _sync_ticker(
    client, conn, ticker: str, cutoff_date: str | None,
) -> tuple[int, str | None]:
    """同步单只 ticker 的 4 张财务表。返回 (总写入行数, 最新 period_end)。"""
    total_rows = 0
    latest: str | None = None
    for st, table in STATEMENT_TABLES:
        rows_added, lp = backfill_statement(client, ticker, st, table, cutoff_date=cutoff_date)
        total_rows += rows_added
        if lp and (latest is None or lp > latest):
            latest = lp
    return total_rows, latest


def backfill_all(tickers: list[str]) -> dict:
    client = get_client()
    conn = get_conn()

    # 分流：新 ticker（全量） vs 已有 ticker（增量近 N 年）
    new_tickers: list[str] = []
    exist_tickers: list[str] = []
    for t in tickers:
        last = get_last_sync(conn, t, SYNC_DATA_TYPE)
        if last is None:
            new_tickers.append(t)
        else:
            exist_tickers.append(t)
    log.info(f"financial: total={len(tickers)}, new={len(new_tickers)}, exist={len(exist_tickers)}")

    cutoff = (date.today() - timedelta(days=RECENT_YEARS * 365)).isoformat()
    total = 0
    ok = 0

    for t in new_tickers:
        try:
            rows_added, latest = _sync_ticker(client, conn, t, cutoff_date=None)
            total += rows_added
            if latest:
                set_sync_ok(conn, t, SYNC_DATA_TYPE, date.fromisoformat(latest), rows_added)
            ok += 1
        except Exception as e:  # noqa: BLE001
            log.error(f"financial {t}: {e}")
            set_sync_error(conn, t, SYNC_DATA_TYPE, str(e))

    for t in exist_tickers:
        try:
            rows_added, latest = _sync_ticker(client, conn, t, cutoff_date=cutoff)
            total += rows_added
            if latest:
                set_sync_ok(conn, t, SYNC_DATA_TYPE, date.fromisoformat(latest), rows_added)
            ok += 1
        except Exception as e:  # noqa: BLE001
            log.error(f"financial {t}: {e}")
            set_sync_error(conn, t, SYNC_DATA_TYPE, str(e))

    conn.close()
    return {"rows": total, "tickers": ok}
