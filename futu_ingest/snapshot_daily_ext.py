"""日频扩展快照：资金流 + 卖空（4 张表，Batch 2）。

append-only 时序，ON DUPLICATE KEY UPDATE 覆盖当期。
capital_flow: period_type=DAY，一次返 ~250 交易日。
capital_distribution: 当日快照。
short_interest / daily_short_volume: 分页，client 已适配 3 值返回。
"""
from __future__ import annotations

import json
import logging
from datetime import date

from core.db_client import get_conn
from futu_ingest.client import clean_date, get_client, to_futu_code
from futu_ingest.concurrency import run_streams, ticker_stream

log = logging.getLogger(__name__)

PAGE_NUM = 50


def snapshot_capital_flow(client, ticker: str) -> int:
    """抓单只日频资金流（~250 行），upsert。返回写入行数。"""
    code = to_futu_code(ticker)
    from futu import PeriodType
    data = client.call("get_capital_flow", code, period_type=PeriodType.DAY)
    if not isinstance(data, (list, dict)) or not data:
        return 0

    items = data if isinstance(data, list) else data.get("capital_flow_list", [])
    rows = []
    for item in items:
        flow_date = clean_date(item.get("date"))
        if flow_date is None:
            continue
        rows.append((
            ticker,
            flow_date,
            item.get("in_flow"),
            item.get("super_in_flow"),
            item.get("big_in_flow"),
            item.get("mid_in_flow"),
            item.get("sml_in_flow"),
            item.get("main_in_flow"),
            json.dumps(item, ensure_ascii=False, default=str),
        ))

    if not rows:
        return 0

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO us_capital_flow "
                "(ticker, date, in_flow, super_in_flow, big_in_flow, "
                " mid_in_flow, sml_in_flow, main_in_flow, raw_payload) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                "ON DUPLICATE KEY UPDATE "
                "  in_flow=VALUES(in_flow), super_in_flow=VALUES(super_in_flow), "
                "  big_in_flow=VALUES(big_in_flow), mid_in_flow=VALUES(mid_in_flow), "
                "  sml_in_flow=VALUES(sml_in_flow), main_in_flow=VALUES(main_in_flow), "
                "  raw_payload=VALUES(raw_payload)",
                rows,
            )
        conn.commit()
    log.info(f"us_capital_flow {ticker}: {len(rows)} rows")
    return len(rows)


def snapshot_capital_dist(client, ticker: str) -> int:
    """抓单只资金分布（当日快照），upsert。返回写入行数（0 或 1）。"""
    code = to_futu_code(ticker)
    data = client.call("get_capital_distribution", code)
    if not isinstance(data, dict) or not data:
        return 0

    today = date.today().isoformat()
    row = (
        ticker, today,
        data.get("capital_in_super"),
        data.get("capital_in_big"),
        data.get("capital_in_mid"),
        data.get("capital_in_small"),
        data.get("capital_out_super"),
        data.get("capital_out_big"),
        data.get("capital_out_mid"),
        data.get("capital_out_small"),
        clean_date(data.get("update_time")),
        json.dumps(data, ensure_ascii=False, default=str),
    )

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO us_capital_distribution "
                "(ticker, date, capital_in_super, capital_in_big, capital_in_mid, "
                " capital_in_small, capital_out_super, capital_out_big, "
                " capital_out_mid, capital_out_small, update_time, raw_payload) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                "ON DUPLICATE KEY UPDATE "
                "  capital_in_super=VALUES(capital_in_super), "
                "  capital_out_super=VALUES(capital_out_super), "
                "  raw_payload=VALUES(raw_payload)",
                row,
            )
        conn.commit()
    log.info(f"us_capital_distribution {ticker}: 1 row")
    return 1


def snapshot_short_interest(client, ticker: str) -> int:
    """抓单只空头持仓（分页），upsert。返回写入行数。"""
    code = to_futu_code(ticker)
    rows = []
    next_key = None
    while True:
        data = client.call(
            "get_short_interest", code,
            next_key=next_key, num=PAGE_NUM,
        )
        if not isinstance(data, (list, dict)) or not data:
            break

        items = data if isinstance(data, list) else data.get("short_interest_list", [])
        for item in items:
            timestamp = clean_date(item.get("timestamp"))
            if timestamp is None:
                continue
            rows.append((
                ticker,
                timestamp,
                item.get("shares_short"),
                item.get("short_percent"),
                item.get("avg_daily_share_volume"),
                item.get("days_to_cover"),
                item.get("close_price"),
                item.get("last_close_price"),
                json.dumps(item, ensure_ascii=False, default=str),
            ))

        if not items or len(items) < PAGE_NUM:
            break
        next_key = data.get("next_key") if isinstance(data, dict) else None

    if not rows:
        return 0

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO us_short_interest "
                "(ticker, timestamp, shares_short, short_percent, avg_daily_share_volume, "
                " days_to_cover, close_price, last_close_price, raw_payload) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                "ON DUPLICATE KEY UPDATE "
                "  shares_short=VALUES(shares_short), short_percent=VALUES(short_percent), "
                "  days_to_cover=VALUES(days_to_cover), raw_payload=VALUES(raw_payload)",
                rows,
            )
        conn.commit()
    log.info(f"us_short_interest {ticker}: {len(rows)} rows")
    return len(rows)


def snapshot_short_volume(client, ticker: str) -> int:
    """抓单只每日卖空量（分页），upsert。返回写入行数。"""
    code = to_futu_code(ticker)
    rows = []
    next_key = None
    while True:
        data = client.call(
            "get_daily_short_volume", code,
            next_key=next_key, num=PAGE_NUM,
        )
        if not isinstance(data, (list, dict)) or not data:
            break

        items = data if isinstance(data, list) else data.get("short_volume_list", [])
        for item in items:
            timestamp = clean_date(item.get("timestamp"))
            if timestamp is None:
                continue
            rows.append((
                ticker,
                timestamp,
                item.get("total_shares_short"),
                item.get("nasdaq_shares_short"),
                item.get("nyse_shares_short"),
                item.get("short_percent"),
                item.get("volume"),
                item.get("close_price"),
                item.get("last_close_price"),
                item.get("daily_trade_avg_ratio"),
                json.dumps(item, ensure_ascii=False, default=str),
            ))

        if not items or len(items) < PAGE_NUM:
            break
        next_key = data.get("next_key") if isinstance(data, dict) else None

    if not rows:
        return 0

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO us_daily_short_volume "
                "(ticker, timestamp, total_shares_short, nasdaq_shares_short, "
                " nyse_shares_short, short_percent, volume, close_price, "
                " last_close_price, daily_trade_avg_ratio, raw_payload) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                "ON DUPLICATE KEY UPDATE "
                "  total_shares_short=VALUES(total_shares_short), "
                "  short_percent=VALUES(short_percent), raw_payload=VALUES(raw_payload)",
                rows,
            )
        conn.commit()
    log.info(f"us_daily_short_volume {ticker}: {len(rows)} rows")
    return len(rows)


def run_daily_ext(tickers: list[str], force: bool = False) -> dict:
    """Batch 2 日频扩展：资金流 + 卖空。"""
    client = get_client()
    r = run_streams([
        ("flow", lambda: ticker_stream(snapshot_capital_flow, client, tickers, "us_capital_flow", force=force)),
        ("dist", lambda: ticker_stream(snapshot_capital_dist, client, tickers, "us_capital_distribution", force=force)),
        ("si",   lambda: ticker_stream(snapshot_short_interest, client, tickers, "us_short_interest", force=force)),
        ("sv",   lambda: ticker_stream(snapshot_short_volume, client, tickers, "us_daily_short_volume", force=force)),
    ])
    return {
        "capital_flow": r["flow"][0],
        "capital_dist": r["dist"][0],
        "short_interest": r["si"][0],
        "short_volume": r["sv"][0],
        "skipped": sum(r[k][2] for k in r),
        "tickers": r["flow"][1],
    }
