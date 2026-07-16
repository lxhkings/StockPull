"""运营效率 backfill（季频，1 张表）。"""
from __future__ import annotations

import json

from apis.futu.client import clean_date, get_client, to_futu_code
from apis.futu.concurrency import ticker_stream
from apis.futu.write_utils import upsert_rows


def backfill_efficiency(client, ticker: str) -> int:
    """抓单只运营效率，upsert。返回写入行数。"""
    code = to_futu_code(ticker)
    data = client.call("get_company_operational_efficiency", code)
    if not isinstance(data, dict) or not data:
        return 0

    items = data.get("item_list", [])
    currency = data.get("currency_code", "USD")
    rows = []
    for item in items:
        rows.append((
            ticker,
            item.get("period_text"),
            clean_date(item.get("end_date")),
            item.get("employee_num"),
            item.get("employee_num_yoy"),
            item.get("income_per_capita"),
            item.get("income_per_capita_yoy"),
            item.get("profit_per_capita"),
            item.get("profit_per_capita_yoy"),
            item.get("net_profit_per_capita"),
            item.get("net_profit_per_capita_yoy"),
            currency,
            json.dumps(item, ensure_ascii=False, default=str),
        ))

    if not rows:
        return 0

    return upsert_rows(
        "us_op_efficiency",
        [
            "ticker", "period_text", "end_date", "employee_num", "employee_num_yoy",
            "income_per_capita", "income_per_capita_yoy", "profit_per_capita",
            "profit_per_capita_yoy", "net_profit_per_capita", "net_profit_per_capita_yoy",
            "currency_code", "raw_payload",
        ],
        rows,
        ["employee_num", "income_per_capita", "profit_per_capita", "raw_payload"],
        ticker=ticker,
    )


def backfill_all(tickers: list[str], force: bool = False) -> dict:
    client = get_client()
    rows, ok, skipped = ticker_stream(backfill_efficiency, client, tickers,
                                      "us_op_efficiency", force=force)
    return {"rows": rows, "tickers": ok, "skipped": skipped}
