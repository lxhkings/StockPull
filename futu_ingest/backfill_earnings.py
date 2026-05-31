"""美股财报发布日 backfill + PIT 回填。

earnings 接口给每期的发布日(pub_time_str)，按 period_text join 回填到
4 张财务表的 ann_date，供下游回测防未来函数。
"""
from __future__ import annotations

import json
import logging

import pandas as pd

from db import get_conn, execute
from futu_ingest.client import get_client, to_futu_code

log = logging.getLogger(__name__)

FIN_TABLES = ("us_fin_income", "us_fin_balance", "us_fin_cashflow", "us_fin_indicator")

# 每张财务表按 period_text join us_earnings_dates 回填 ann_date
PIT_BACKFILL_SQL = {
    tbl: (
        f"UPDATE {tbl} f "
        "JOIN us_earnings_dates e "
        "  ON f.ticker = e.ticker AND f.period_text = e.period_text "
        "SET f.ann_date = e.pub_date "
        "WHERE e.pub_date IS NOT NULL"
    )
    for tbl in FIN_TABLES
}


def _date_part(s):
    """'2026-04-30 17:00:00' -> '2026-04-30'；空值返回 None。"""
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return None
    s = str(s).strip()
    return s.split(" ")[0] if s else None


def backfill_earnings(client, ticker: str) -> int:
    code = to_futu_code(ticker)
    df = client.call("get_financials_earnings_price_history", code)
    if df is None or not hasattr(df, "iterrows") or len(df) == 0:
        return 0
    rows = []
    for _, r in df.iterrows():
        period_text = r.get("period_text")
        if not period_text:
            continue
        payload = {k: (None if pd.isna(v) else v) for k, v in r.items()}
        rows.append((
            ticker,
            period_text,
            str(r.get("fiscal_year") or ""),
            str(r.get("financial_type") or ""),
            _date_part(r.get("pub_time_str")),
            json.dumps(payload, ensure_ascii=False, default=str),
        ))
    if not rows:
        return 0
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO us_earnings_dates "
                "(ticker, period_text, fiscal_year, financial_type, pub_date, raw_payload) "
                "VALUES (%s,%s,%s,%s,%s,%s) "
                "ON DUPLICATE KEY UPDATE "
                "  fiscal_year=VALUES(fiscal_year), financial_type=VALUES(financial_type), "
                "  pub_date=VALUES(pub_date), raw_payload=VALUES(raw_payload)",
                rows,
            )
        conn.commit()
    log.info(f"us_earnings_dates {ticker}: {len(rows)} rows")
    return len(rows)


def run_pit_backfill() -> dict:
    """把 us_earnings_dates.pub_date 回填到 4 张财务表的 ann_date。"""
    result = {}
    for tbl, sql in PIT_BACKFILL_SQL.items():
        result[tbl] = execute(sql)
    log.info(f"PIT backfill: {result}")
    return result


def backfill_all(tickers: list[str]) -> dict:
    client = get_client()
    total = 0
    for t in tickers:
        try:
            total += backfill_earnings(client, t)
        except Exception as e:  # noqa: BLE001
            log.error(f"earnings {t}: {e}")
    pit = run_pit_backfill()
    return {"earnings_rows": total, "tickers": len(tickers), "pit": pit}
