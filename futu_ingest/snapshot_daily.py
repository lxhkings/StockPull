"""美股每日快照：流通股本 + 分析师一致预期。

这两类数据接口只返当前值（分析师预期无历史），必须每日抓存累积时序。
"""
from __future__ import annotations

import json
import logging
from datetime import date

import pandas as pd

from db import get_conn
from futu_ingest.client import get_client, to_futu_code, from_futu_code

log = logging.getLogger(__name__)

SNAPSHOT_BATCH = 200   # get_market_snapshot 单次最多 400，留余量


def _num(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    return v


def snapshot_shares(client, tickers: list[str]) -> int:
    """批量抓快照，写当日流通股/市值。返回写入行数。"""
    today = date.today().isoformat()
    rows = []
    for i in range(0, len(tickers), SNAPSHOT_BATCH):
        batch = [to_futu_code(t) for t in tickers[i:i + SNAPSHOT_BATCH]]
        df = client.call("get_market_snapshot", batch)
        if df is None or not hasattr(df, "iterrows"):
            continue
        for _, r in df.iterrows():
            tk = from_futu_code(r.get("code"))
            payload = {k: _num(v) for k, v in r.items()}
            rows.append((
                tk, today,
                _num(r.get("issued_shares")),
                _num(r.get("outstanding_shares")),
                _num(r.get("total_market_val")),
                _num(r.get("circular_market_val")),
                json.dumps(payload, ensure_ascii=False, default=str),
            ))
    if not rows:
        return 0
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO us_shares_daily "
                "(ticker, date, issued_shares, outstanding_shares, "
                " total_market_val, circular_market_val, raw_payload) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s) "
                "ON DUPLICATE KEY UPDATE "
                "  issued_shares=VALUES(issued_shares), "
                "  outstanding_shares=VALUES(outstanding_shares), "
                "  total_market_val=VALUES(total_market_val), "
                "  circular_market_val=VALUES(circular_market_val), "
                "  raw_payload=VALUES(raw_payload)",
                rows,
            )
        conn.commit()
    log.info(f"us_shares_daily {today}: {len(rows)} rows")
    return len(rows)


def snapshot_analyst(client, ticker: str) -> int:
    today = date.today().isoformat()
    data = client.call("get_research_analyst_consensus", to_futu_code(ticker))
    if not isinstance(data, dict) or not data:
        return 0
    params = (
        ticker, today,
        _num(data.get("highest")), _num(data.get("average")), _num(data.get("lowest")),
        data.get("rating"), _num(data.get("total")),
        _num(data.get("buy")), _num(data.get("hold")), _num(data.get("sell")),
        json.dumps(data, ensure_ascii=False, default=str),
    )
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO us_analyst_consensus "
                "(ticker, snapshot_date, target_high, target_avg, target_low, "
                " rating, total_analysts, buy_pct, hold_pct, sell_pct, raw_payload) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                "ON DUPLICATE KEY UPDATE "
                "  target_high=VALUES(target_high), target_avg=VALUES(target_avg), "
                "  target_low=VALUES(target_low), rating=VALUES(rating), "
                "  total_analysts=VALUES(total_analysts), buy_pct=VALUES(buy_pct), "
                "  hold_pct=VALUES(hold_pct), sell_pct=VALUES(sell_pct), "
                "  raw_payload=VALUES(raw_payload)",
                params,
            )
        conn.commit()
    return 1


def run_daily(tickers: list[str]) -> dict:
    client = get_client()
    shares = snapshot_shares(client, tickers)
    analyst = 0
    for t in tickers:
        try:
            analyst += snapshot_analyst(client, t)
        except Exception as e:  # noqa: BLE001
            log.error(f"analyst {t}: {e}")
    return {"shares": shares, "analyst": analyst, "tickers": len(tickers)}
