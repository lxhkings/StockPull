"""股东 + 内部人 backfill（季频，5 张表）。

- us_shareholders_overview: 股东概览（main + type 合并）
- us_holding_changes: 股东增减持
- us_institutional: 机构持仓汇总
- us_insider_holders: 内部人持股（时序）
- us_insider_trades: 内部人交易（Form 4）
"""
from __future__ import annotations

import json
from datetime import date

from apis.futu.client import clean_date, get_client, to_futu_code
from apis.futu.concurrency import run_streams, ticker_stream
from apis.futu.write_utils import upsert_rows


def backfill_overview(client, ticker: str) -> int:
    """抓单只股东概览，upsert。返回写入行数。"""
    code = to_futu_code(ticker)
    data = client.call("get_shareholders_overview", code)
    if not isinstance(data, dict) or not data:
        return 0

    periods = data.get("holding_period", [])
    period_text = periods[0] if periods else ""

    rows = []
    for h in data.get("main_holder", []):
        rows.append((
            ticker, period_text, "main",
            h.get("holder_name"), h.get("holder_pct"), h.get("holder_id"),
            json.dumps(h, ensure_ascii=False, default=str),
        ))

    for h in data.get("holder_type", []):
        rows.append((
            ticker, period_text, "type",
            h.get("holder_name"), h.get("holder_pct"), None,
            json.dumps(h, ensure_ascii=False, default=str),
        ))

    if not rows:
        return 0

    return upsert_rows(
        "us_shareholders_overview",
        ["ticker", "period_text", "holder_category", "holder_name", "holder_pct",
         "holder_id", "raw_payload"],
        rows,
        ["holder_pct", "holder_id", "raw_payload"],
        ticker=ticker,
    )


def backfill_holding_changes(client, ticker: str) -> int:
    """抓单只股东增减持，upsert。返回写入行数。"""
    code = to_futu_code(ticker)
    data = client.call("get_shareholders_holding_changes", code)
    if not isinstance(data, (list, dict)) or not data:
        return 0

    items = data if isinstance(data, list) else data.get("holding_change_list", [])
    rows = []
    for h in items:
        rows.append((
            ticker,
            h.get("period_text"),
            h.get("holder_id"),
            h.get("holder_name"),
            h.get("holder_type"),
            h.get("share_change_num"),
            h.get("shares_change_price"),
            h.get("share_ratio"),
            clean_date(h.get("holding_date")),
            json.dumps(h, ensure_ascii=False, default=str),
        ))

    if not rows:
        return 0

    return upsert_rows(
        "us_holding_changes",
        ["ticker", "period_text", "holder_id", "holder_name", "holder_type",
         "share_change_num", "shares_change_price", "share_ratio", "holding_date", "raw_payload"],
        rows,
        ["share_change_num", "shares_change_price", "share_ratio", "raw_payload"],
        ticker=ticker,
    )


def backfill_institutional(client, ticker: str) -> int:
    """抓单只机构持仓汇总，upsert。返回写入行数。"""
    code = to_futu_code(ticker)
    data = client.call("get_shareholders_institutional", code)
    if not isinstance(data, dict) or not data:
        return 0

    row = (
        ticker,
        data.get("period_text"),
        data.get("institution_quantity"),
        data.get("institution_qty_change"),
        data.get("holder_quantity"),
        data.get("holder_qty_change"),
        data.get("holder_pct"),
        data.get("holder_pct_change"),
        clean_date(data.get("update_time")),
        json.dumps(data, ensure_ascii=False, default=str),
    )

    return upsert_rows(
        "us_institutional",
        ["ticker", "period_text", "institution_quantity", "institution_qty_change",
         "holder_quantity", "holder_qty_change", "holder_pct", "holder_pct_change",
         "update_time", "raw_payload"],
        [row],
        ["institution_quantity", "holder_quantity", "holder_pct", "raw_payload"],
        ticker=ticker,
    )


def backfill_insider_holders(client, ticker: str) -> int:
    """抓单只内部人持股（时序），upsert。返回写入行数。"""
    code = to_futu_code(ticker)
    data = client.call("get_insider_holder_list", code)
    if not isinstance(data, (list, dict)) or not data:
        return 0

    items = data if isinstance(data, list) else data.get("insider_holder_list", [])
    today = date.today().isoformat()
    rows = []
    for h in items:
        rows.append((
            ticker,
            h.get("holder_id"),
            h.get("holder_name"),
            h.get("title"),
            h.get("holder_quantity"),
            h.get("holder_pct"),
            h.get("all_count"),
            h.get("insider_total_count"),
            h.get("insider_bought_count"),
            h.get("insider_sold_count"),
            today,
            json.dumps(h, ensure_ascii=False, default=str),
        ))

    if not rows:
        return 0

    return upsert_rows(
        "us_insider_holders",
        ["ticker", "holder_id", "holder_name", "title", "holder_quantity", "holder_pct",
         "all_count", "insider_total_count", "insider_bought_count", "insider_sold_count",
         "snapshot_date", "raw_payload"],
        rows,
        ["holder_quantity", "holder_pct", "all_count", "raw_payload"],
        ticker=ticker,
    )


def backfill_insider_trades(client, ticker: str) -> int:
    """抓单只内部人交易（Form 4），upsert。返回写入行数。"""
    code = to_futu_code(ticker)
    data = client.call("get_insider_trade_list", code)
    if not isinstance(data, (list, dict)) or not data:
        return 0

    items = data if isinstance(data, list) else data.get("insider_trade_list", [])
    rows = []
    for h in items:
        min_trade_date = clean_date(h.get("min_trade_date"))
        if min_trade_date is None:
            continue
        rows.append((
            ticker,
            h.get("holder_id"),
            min_trade_date,
            h.get("holder_name"),
            h.get("title"),
            h.get("transaction_type"),
            h.get("trade_shares"),
            h.get("min_price"),
            h.get("max_price"),
            h.get("security_holder_quantity"),
            h.get("security_description"),
            h.get("source_group_name"),
            json.dumps(h, ensure_ascii=False, default=str),
        ))

    if not rows:
        return 0

    return upsert_rows(
        "us_insider_trades",
        ["ticker", "holder_id", "min_trade_date", "holder_name", "title",
         "transaction_type", "trade_shares", "min_price", "max_price",
         "security_holder_quantity", "security_description", "source_group_name",
         "raw_payload"],
        rows,
        ["trade_shares", "min_price", "max_price", "raw_payload"],
        ticker=ticker,
    )


def backfill_all(tickers: list[str], force: bool = False) -> dict:
    client = get_client()
    r = run_streams([
        ("overview", lambda: ticker_stream(backfill_overview, client, tickers, "us_shareholders_overview", force=force)),
        ("changes",  lambda: ticker_stream(backfill_holding_changes, client, tickers, "us_holding_changes", force=force)),
        ("inst",     lambda: ticker_stream(backfill_institutional, client, tickers, "us_institutional", force=force)),
        ("holders",  lambda: ticker_stream(backfill_insider_holders, client, tickers, "us_insider_holders", force=force)),
        ("trades",   lambda: ticker_stream(backfill_insider_trades, client, tickers, "us_insider_trades", force=force)),
    ])
    return {
        "overview_rows": r["overview"][0],
        "changes_rows": r["changes"][0],
        "institutional_rows": r["inst"][0],
        "insider_holders_rows": r["holders"][0],
        "insider_trades_rows": r["trades"][0],
        "skipped": sum(r[k][2] for k in r),
        "tickers": r["overview"][1],
    }
