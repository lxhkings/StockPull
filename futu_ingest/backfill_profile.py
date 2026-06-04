"""公司元数据 backfill（月频）。EAV 模式：field_name / field_value。"""
from __future__ import annotations

import logging
from datetime import date

from db import get_conn
from futu_ingest.client import get_client, to_futu_code
from futu_ingest.concurrency import ticker_stream

log = logging.getLogger(__name__)

SYNC_DATA_TYPE = "us_profile"


def backfill_profile(client, ticker: str) -> int:
    """抓单只公司元数据，upsert。返回写入行数。"""
    code = to_futu_code(ticker)
    data = client.call("get_company_profile", code)
    if not isinstance(data, (list, dict)) or not data:
        return 0

    # data 可能是 list[dict] 或 dict，统一处理
    fields = data if isinstance(data, list) else data.get("profile_list", [])
    today = date.today().isoformat()
    rows = []
    for f in fields:
        name = f.get("field_name")
        if not name:
            continue
        rows.append((
            ticker,
            name,
            f.get("field_value"),
            today,
        ))

    if not rows:
        return 0

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO us_company_profile "
                "(ticker, field_name, field_value, updated_at) "
                "VALUES (%s,%s,%s,%s) "
                "ON DUPLICATE KEY UPDATE "
                "  field_value=VALUES(field_value), updated_at=VALUES(updated_at)",
                rows,
            )
        conn.commit()
    log.info(f"us_company_profile {ticker}: {len(rows)} fields")
    return len(rows)


def backfill_all(tickers: list[str], force: bool = False) -> dict:
    client = get_client()
    rows, ok, skipped = ticker_stream(backfill_profile, client, tickers,
                                      "us_company_profile", force=force)
    return {"rows": rows, "tickers": ok, "skipped": skipped}
