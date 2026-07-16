"""美股分红 + 拆股 backfill。"""
from __future__ import annotations

import json

from apis.futu.client import clean_date, get_client, to_futu_code
from apis.futu.concurrency import run_streams, ticker_stream
from apis.futu.write_utils import paginate_call, upsert_rows

PAGE_NUM = 50


def backfill_dividends(client, ticker: str) -> int:
    code = to_futu_code(ticker)
    data = client.call("get_corporate_actions_dividends", code)
    div_list = (data or {}).get("dividend_list", []) if isinstance(data, dict) else []
    rows = []
    for d in div_list:
        ex_date = clean_date(d.get("ex_date"))
        if ex_date is None:
            continue
        rows.append((
            ticker,
            ex_date,
            clean_date(d.get("pub_date")),
            clean_date(d.get("record_date")),
            clean_date(d.get("dividend_payable_date")),
            json.dumps(d, ensure_ascii=False, default=str),
        ))
    if not rows:
        return 0
    return upsert_rows(
        "us_dividends",
        ["ticker", "ex_date", "pub_date", "record_date", "payable_date", "raw_payload"],
        rows,
        ["pub_date", "record_date", "payable_date", "raw_payload"],
        ticker=ticker,
    )


def backfill_splits(client, ticker: str) -> int:
    code = to_futu_code(ticker)
    split_list = paginate_call(
        client,
        "get_corporate_actions_stock_splits",
        code,
        list_key="split_list",
        page_num=PAGE_NUM,
    )
    rows = []
    for s in split_list:
        ex_date = clean_date(s.get("ex_date"))
        if ex_date is None:
            continue
        rows.append((
            ticker,
            ex_date,
            json.dumps(s, ensure_ascii=False, default=str),
        ))
    if not rows:
        return 0
    return upsert_rows(
        "us_splits",
        ["ticker", "ex_date", "raw_payload"],
        rows,
        ["raw_payload"],
        ticker=ticker,
    )


def backfill_all(tickers: list[str], force: bool = False) -> dict:
    client = get_client()
    r = run_streams([
        ("div",   lambda: ticker_stream(backfill_dividends, client, tickers, "us_dividends", force=force)),
        ("split", lambda: ticker_stream(backfill_splits, client, tickers, "us_splits", force=force)),
    ])
    return {
        "dividends": r["div"][0], "splits": r["split"][0],
        "skipped": r["div"][2] + r["split"][2], "tickers": r["div"][1],
    }
