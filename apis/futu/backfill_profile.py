"""公司元数据 backfill（月频）。EAV 模式：field_name / field_value。"""
from __future__ import annotations

from datetime import date

from apis.futu.client import get_client, to_futu_code
from apis.futu.concurrency import ticker_stream
from apis.futu.write_utils import upsert_rows


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

    return upsert_rows(
        "us_company_profile",
        ["ticker", "field_name", "field_value", "updated_at"],
        rows,
        ["field_value", "updated_at"],
        ticker=ticker,
    )


def backfill_all(tickers: list[str], force: bool = False) -> dict:
    client = get_client()
    rows, ok, skipped = ticker_stream(backfill_profile, client, tickers,
                                      "us_company_profile", force=force)
    return {"rows": rows, "tickers": ok, "skipped": skipped}
