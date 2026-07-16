"""周频快照：估值 + 评级 + Morningstar（3 张表）。

append-only 时序，ON DUPLICATE KEY UPDATE 覆盖当期。
"""
from __future__ import annotations

import json
from datetime import date

from apis.futu.client import clean_date, get_client, to_futu_code
from apis.futu.concurrency import run_streams, ticker_stream
from apis.futu.write_utils import upsert_rows

PAGE_NUM = 50


def snapshot_valuation(client, ticker: str) -> int:
    """抓单只估值快照，upsert。返回写入行数（0 或 1）。"""
    code = to_futu_code(ticker)
    data = client.call("get_valuation_detail", code)
    if not isinstance(data, dict) or not data:
        return 0

    today = date.today().isoformat()
    trend = data.get("trend", {})
    plate = data.get("plate_distribution", {})

    row = (
        ticker, today,
        trend.get("current_value"),  # pe_ttm
        data.get("pe_percentile"),
        trend.get("average_value"),  # pe_avg
        data.get("pb"),
        data.get("pb_percentile"),
        data.get("ps_ttm"),
        data.get("ps_percentile"),
        plate.get("plate"),
        plate.get("plate_name"),
        plate.get("plate_ranking"),
        json.dumps(data, ensure_ascii=False, default=str),
    )

    return upsert_rows(
        "us_valuation_snapshot",
        ["ticker", "snapshot_date", "pe_ttm", "pe_percentile", "pe_avg",
         "pb", "pb_percentile", "ps_ttm", "ps_percentile",
         "plate_code", "plate_name", "plate_ranking", "raw_payload"],
        [row],
        ["pe_ttm", "pe_percentile", "pb", "pb_percentile",
         "ps_ttm", "ps_percentile", "plate_ranking", "raw_payload"],
        ticker=ticker,
    )


def snapshot_rating(client, ticker: str) -> int:
    """抓单只评级变动（分页），upsert。返回写入行数。"""
    code = to_futu_code(ticker)
    rows = []
    next_key = None
    while True:
        kwargs = {"num": PAGE_NUM}
        if next_key is not None:
            kwargs["next_key"] = next_key
        data = client.call("get_research_rating_summary", code, **kwargs)
        if not isinstance(data, dict) or not data:
            break

        items = data.get("inst_rating_summary_list", [])
        today = date.today().isoformat()
        for item in items:
            rows.append((
                ticker, today,
                item.get("institution_uid"),
                item.get("institution_name"),
                item.get("institution_picture_url"),
                item.get("rating"),
                item.get("target_price"),
                clean_date(item.get("update_time")),
                json.dumps(item, ensure_ascii=False, default=str),
            ))

        next_key = data.get("next_key", "-1")
        if not items or next_key == "-1":
            break

    if not rows:
        return 0

    return upsert_rows(
        "us_rating_summary",
        ["ticker", "snapshot_date", "institution_uid", "institution_name",
         "institution_picture_url", "rating", "target_price", "update_time", "raw_payload"],
        rows,
        ["rating", "target_price", "update_time", "raw_payload"],
        ticker=ticker,
    )


def snapshot_morningstar(client, ticker: str) -> int:
    """抓单只 Morningstar 评级，upsert。返回写入行数（0 或 1）。"""
    code = to_futu_code(ticker)
    data = client.call("get_research_morningstar_report", code)
    if not isinstance(data, dict) or not data:
        return 0

    today = date.today().isoformat()
    row = (
        ticker, today,
        data.get("star_rating"),
        clean_date(data.get("star_update_time")),
        data.get("fair_value"),
        data.get("economic_moat_label"),
        data.get("uncertainty_label"),
        data.get("capital_allocation_label"),
        data.get("analyst_report_by_line"),
        clean_date(data.get("analyst_update_time")),
        json.dumps(data, ensure_ascii=False, default=str),
    )

    return upsert_rows(
        "us_morningstar",
        ["ticker", "snapshot_date", "star_rating", "star_update_time", "fair_value",
         "economic_moat", "uncertainty", "capital_allocation", "analyst_name",
         "analyst_update_time", "raw_payload"],
        [row],
        ["star_rating", "fair_value", "economic_moat", "uncertainty", "raw_payload"],
        ticker=ticker,
    )


def run_weekly(tickers: list[str], force: bool = False) -> dict:
    client = get_client()
    r = run_streams([
        ("val",     lambda: ticker_stream(snapshot_valuation, client, tickers, "us_valuation_snapshot", force=force)),
        ("rating",  lambda: ticker_stream(snapshot_rating, client, tickers, "us_rating_summary", force=force)),
        ("morning", lambda: ticker_stream(snapshot_morningstar, client, tickers, "us_morningstar", force=force)),
    ])
    return {
        "valuation": r["val"][0],
        "rating": r["rating"][0],
        "morningstar": r["morning"][0],
        "skipped": sum(r[k][2] for k in r),
        "tickers": r["val"][1],
    }
