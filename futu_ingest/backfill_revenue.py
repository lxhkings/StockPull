"""分部营收 + 财报日涨跌 backfill（季频）。

revenue_breakdown: screen_date_list 逐期回填，限近 RECENT_PERIODS 期。
earnings_price_move: 一次返回全量（~110 行），直接 upsert。
"""
from __future__ import annotations

import json
import logging
from datetime import date

from db import get_conn
from futu_ingest.client import get_client, to_futu_code
from futu_ingest.concurrency import run_streams, ticker_stream

log = logging.getLogger(__name__)

SYNC_DATA_TYPE = "us_revenue"
RECENT_PERIODS = 10  # 限近 ~10 期（2-3 年），避免 71 期全量导致 21hr runtime


def backfill_revenue(client, ticker: str) -> int:
    """抓单只分部营收（逐期），upsert。返回写入行数。"""
    code = to_futu_code(ticker)
    data = client.call("get_financials_revenue_breakdown", code)
    if not isinstance(data, dict) or not data:
        return 0

    today = date.today().isoformat()
    rows: list[tuple] = []

    # 首次返回的当前期
    for item in data.get("breakdown_list", []):
        typ = item.get("type", 8)
        for entry in item.get("item_list", []):
            rows.append((
                ticker,
                data.get("screen_date_list", [{}])[0].get("period_text", ""),
                typ,
                entry.get("name", ""),
                entry.get("main_oper_income"),
                entry.get("ratio"),
                today,
            ))

    # 逐期回填（限近 N 期）
    screen_dates = data.get("screen_date_list", [])[1:]  # 跳过首个（已处理）
    for sd in screen_dates[:RECENT_PERIODS]:
        try:
            period_data = client.call(
                "get_financials_revenue_breakdown",
                code,
                date=sd.get("date"),
                financial_type=sd.get("financial_type"),
            )
            if not isinstance(period_data, dict):
                continue
            for item in period_data.get("breakdown_list", []):
                typ = item.get("type", 8)
                for entry in item.get("item_list", []):
                    rows.append((
                        ticker,
                        sd.get("period_text", ""),
                        typ,
                        entry.get("name", ""),
                        entry.get("main_oper_income"),
                        entry.get("ratio"),
                        today,
                    ))
        except Exception as e:  # noqa: BLE001
            log.warning(f"revenue {ticker} {sd.get('period_text')}: {e}")

    if not rows:
        return 0

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO us_revenue_breakdown "
                "(ticker, period_text, type, item_name, main_oper_income, ratio, updated_at) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s) "
                "ON DUPLICATE KEY UPDATE "
                "  main_oper_income=VALUES(main_oper_income), ratio=VALUES(ratio), "
                "  updated_at=VALUES(updated_at)",
                rows,
            )
        conn.commit()
    log.info(f"us_revenue_breakdown {ticker}: {len(rows)} rows")
    return len(rows)


def backfill_earnings_move(client, ticker: str) -> int:
    """抓单只财报日涨跌，upsert。返回写入行数。"""
    code = to_futu_code(ticker)
    data = client.call("get_financials_earnings_price_move", code)
    if not isinstance(data, (list, dict)) or not data:
        return 0

    items = data if isinstance(data, list) else data.get("price_move_list", [])
    rows = []
    for item in items:
        rows.append((
            ticker,
            item.get("period_text"),
            item.get("day_offset"),
            item.get("fiscal_year"),
            item.get("financial_type"),
            item.get("pub_trading_day"),
            item.get("trading_day"),
            item.get("open"),
            item.get("close"),
            item.get("high"),
            item.get("low"),
            item.get("volume"),
            item.get("turnover"),
            item.get("implied_vol"),
            item.get("history_vol"),
            json.dumps(item, ensure_ascii=False, default=str),
        ))

    if not rows:
        return 0

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO us_earnings_price_move "
                "(ticker, period_text, day_offset, fiscal_year, financial_type, "
                " pub_trading_day, trading_day, open, close, high, low, volume, "
                " turnover, implied_vol, history_vol, raw_payload) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                "ON DUPLICATE KEY UPDATE "
                "  open=VALUES(open), close=VALUES(close), high=VALUES(high), "
                "  low=VALUES(low), volume=VALUES(volume), turnover=VALUES(turnover), "
                "  raw_payload=VALUES(raw_payload)",
                rows,
            )
        conn.commit()
    log.info(f"us_earnings_price_move {ticker}: {len(rows)} rows")
    return len(rows)


def backfill_all(tickers: list[str]) -> dict:
    client = get_client()
    r = run_streams([
        ("rev",  lambda: ticker_stream(backfill_revenue, client, tickers, "revenue")),
        ("move", lambda: ticker_stream(backfill_earnings_move, client, tickers, "earnings_move")),
    ])
    return {"revenue_rows": r["rev"][0], "earnings_move_rows": r["move"][0], "tickers": r["rev"][1]}
