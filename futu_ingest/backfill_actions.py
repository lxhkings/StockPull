"""美股分红 + 拆股 backfill。"""
from __future__ import annotations

import json
import logging

from db import get_conn
from futu_ingest.client import get_client, to_futu_code
from futu_ingest.concurrency import run_streams, ticker_stream

log = logging.getLogger(__name__)

PAGE_NUM = 50


def backfill_dividends(client, ticker: str) -> int:
    code = to_futu_code(ticker)
    data = client.call("get_corporate_actions_dividends", code)
    div_list = (data or {}).get("dividend_list", []) if isinstance(data, dict) else []
    rows = []
    for d in div_list:
        if not d.get("ex_date"):
            continue
        rows.append((
            ticker,
            d.get("ex_date"),
            d.get("pub_date"),
            d.get("record_date"),
            d.get("dividend_payable_date"),
            json.dumps(d, ensure_ascii=False, default=str),
        ))
    if not rows:
        return 0
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO us_dividends "
                "(ticker, ex_date, pub_date, record_date, payable_date, raw_payload) "
                "VALUES (%s,%s,%s,%s,%s,%s) "
                "ON DUPLICATE KEY UPDATE "
                "  pub_date=VALUES(pub_date), record_date=VALUES(record_date), "
                "  payable_date=VALUES(payable_date), raw_payload=VALUES(raw_payload)",
                rows,
            )
        conn.commit()
    log.info(f"us_dividends {ticker}: {len(rows)} rows")
    return len(rows)


def backfill_splits(client, ticker: str) -> int:
    code = to_futu_code(ticker)
    rows = []
    next_key = None
    while True:
        data = client.call("get_corporate_actions_stock_splits", code,
                           next_key=next_key, num=PAGE_NUM)
        split_list = (data or {}).get("split_list", []) if isinstance(data, dict) else []
        for s in split_list:
            if not s.get("ex_date"):
                continue
            rows.append((ticker, s.get("ex_date"),
                         json.dumps(s, ensure_ascii=False, default=str)))
        next_key = (data or {}).get("next_key", "-1") if isinstance(data, dict) else "-1"
        if not split_list or next_key == "-1":
            break
    if not rows:
        return 0
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO us_splits (ticker, ex_date, raw_payload) "
                "VALUES (%s,%s,%s) "
                "ON DUPLICATE KEY UPDATE raw_payload=VALUES(raw_payload)",
                rows,
            )
        conn.commit()
    log.info(f"us_splits {ticker}: {len(rows)} rows")
    return len(rows)


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
