"""美股每日快照：流通股本 + 分析师一致预期。

这两类数据接口只返当前值（分析师预期无历史），必须每日抓存累积时序。
"""
from __future__ import annotations

import json
from datetime import date

from config import FUTU_REFRESH_DAYS
from apis.futu.client import get_client, to_futu_code, from_futu_code
from core.batch_utils import chunked
from core.http_utils import or_none
from apis.futu.concurrency import batch_with_bisect, run_streams, ticker_stream
from apis.futu.sync import fresh_tickers, mark_ok
from apis.futu.write_utils import upsert_rows

SNAPSHOT_BATCH = 200   # get_market_snapshot 单次最多 400，留余量


def _num(v):
    return or_none(v)



def _share_row(r, today: str) -> tuple:
    """snapshot 行 -> us_shares_daily 入库元组。"""
    payload = {k: _num(v) for k, v in r.items()}
    return (
        from_futu_code(r.get("code")), today,
        _num(r.get("issued_shares")),
        _num(r.get("outstanding_shares")),
        _num(r.get("total_market_val")),
        _num(r.get("circular_market_val")),
        json.dumps(payload, ensure_ascii=False, default=str),
    )


def snapshot_shares(client, tickers: list[str]) -> int:
    """批量抓快照，写当日流通股/市值。返回写入行数。未知票经二分隔离跳过。"""
    today = date.today().isoformat()
    rows = []
    for batch_tickers in chunked(tickers, SNAPSHOT_BATCH):
        batch = [to_futu_code(t) for t in batch_tickers]
        for df in batch_with_bisect(client, "get_market_snapshot", batch):
            if df is None or not hasattr(df, "iterrows"):
                continue
            rows.extend(_share_row(r, today) for _, r in df.iterrows())
    if not rows:
        return 0
    return upsert_rows(
        "us_shares_daily",
        ["ticker", "date", "issued_shares", "outstanding_shares",
         "total_market_val", "circular_market_val", "raw_payload"],
        rows,
        ["issued_shares", "outstanding_shares", "total_market_val",
         "circular_market_val", "raw_payload"],
    )


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
    return upsert_rows(
        "us_analyst_consensus",
        ["ticker", "snapshot_date", "target_high", "target_avg", "target_low",
         "rating", "total_analysts", "buy_pct", "hold_pct", "sell_pct", "raw_payload"],
        [params],
        ["target_high", "target_avg", "target_low", "rating",
         "total_analysts", "buy_pct", "hold_pct", "sell_pct", "raw_payload"],
        ticker=ticker,
    )


def sync_shares(client, tickers: list[str], force: bool = False) -> tuple[int, int, int]:
    """批量流通股快照，哨兵 __ALL__ 按日节流。返回 (rows, ok, skipped)。"""
    if not force:
        rd = FUTU_REFRESH_DAYS["us_shares_daily"]
        if "__ALL__" in fresh_tickers("us_shares_daily", rd):
            return 0, 0, 1
    n = snapshot_shares(client, tickers)
    mark_ok("__ALL__", "us_shares_daily", n)
    return n, 1, 0


def run_daily(tickers: list[str], force: bool = False) -> dict:
    client = get_client()
    r = run_streams([
        ("shares",  lambda: sync_shares(client, tickers, force=force)),
        ("analyst", lambda: ticker_stream(snapshot_analyst, client, tickers,
                                          "us_analyst_consensus", force=force)),
    ])
    return {"shares": r["shares"][0], "analyst": r["analyst"][0],
            "skipped": r["shares"][2] + r["analyst"][2], "tickers": len(tickers)}
