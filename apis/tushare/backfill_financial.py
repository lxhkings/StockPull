"""A 股财务三表 + 财务指标，使用 Tushare VIP 全市场单期接口。"""
from __future__ import annotations

import logging
from datetime import date

from config import TUSHARE_BACKFILL_START
from core.db_client import get_conn
from apis.tushare.client import get_client
from apis.tushare.transform_financial import transform_financial_rows

log = logging.getLogger(__name__)

# (api_name, target_table, has_report_type)
FINANCIAL_APIS: list[tuple[str, str, bool]] = [
    ("income_vip",        "fin_income",       True),
    ("balancesheet_vip",  "fin_balancesheet", True),
    ("cashflow_vip",      "fin_cashflow",     True),
    ("fina_indicator_vip", "fin_indicator",    False),
]

QUARTER_ENDS = ("0331", "0630", "0930", "1231")


def quarterly_periods(start_yyyymmdd: str, end_yyyymmdd: str) -> list[str]:
    """从 start 年到 end 年每季度的 YYYYMMDD 字符串。"""
    start_year = int(start_yyyymmdd[:4])
    end_year = int(end_yyyymmdd[:4])
    periods: list[str] = []
    for y in range(start_year, end_year + 1):
        for q in QUARTER_ENDS:
            p = f"{y}{q}"
            if start_yyyymmdd <= p <= end_yyyymmdd:
                periods.append(p)
    return periods


def backfill_period(api_name: str, table: str, period: str) -> int:
    client = get_client()
    df = client.call(api_name, period=period)
    if df is None or df.empty:
        return 0
    has_report_type = api_name != "fina_indicator_vip"
    rows = transform_financial_rows(df, has_report_type)

    with get_conn() as conn:
        with conn.cursor() as cur:
            if has_report_type:
                cur.executemany(
                    f"INSERT INTO {table} "
                    "(ts_code, end_date, ann_date, f_ann_date, report_type, comp_type, raw_payload) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s) "
                    "ON DUPLICATE KEY UPDATE "
                    "  ann_date=VALUES(ann_date), f_ann_date=VALUES(f_ann_date), "
                    "  comp_type=VALUES(comp_type), raw_payload=VALUES(raw_payload)",
                    rows,
                )
            else:
                cur.executemany(
                    f"INSERT INTO {table} (ts_code, end_date, ann_date, raw_payload) "
                    "VALUES (%s,%s,%s,%s) "
                    "ON DUPLICATE KEY UPDATE "
                    "  ann_date=VALUES(ann_date), raw_payload=VALUES(raw_payload)",
                    rows,
                )
        conn.commit()
    log.info(f"{api_name}@{period}: {len(rows)} rows")
    return len(rows)


def backfill_all(periods: list[str] | None = None,
                 start: str = TUSHARE_BACKFILL_START) -> dict:
    if periods is None:
        today = date.today().strftime("%Y%m%d")
        periods = quarterly_periods(start, today)
    log.info(f"financial backfill: {len(periods)} periods × {len(FINANCIAL_APIS)} apis "
             f"= {len(periods) * len(FINANCIAL_APIS)} calls")
    total = 0
    for p in periods:
        for api_name, table, _ in FINANCIAL_APIS:
            try:
                total += backfill_period(api_name, table, p)
            except Exception as e:
                log.error(f"{api_name}@{p}: {e}")
    return {"rows": total, "periods": len(periods)}
