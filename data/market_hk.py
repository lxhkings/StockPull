"""HK market module: thin adapter exposing the MarketModule protocol.

Wraps index_updater_hk.update_hsi() and stock_updater_hk.update_prices_batch()
into the Pipeline contract.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Optional

import akshare as ak

from config import START_DATE_HK, AKSHARE_RETRY_COUNT, AKSHARE_RETRY_DELAY
from db import get_conn, get_index_tickers, query, execute
from data import index_updater_hk
from data import stock_updater_hk
from data.base import to_float

log = logging.getLogger(__name__)

market_id = "hk"


def update_index() -> tuple[list[str], int, int]:
    """Run HSI snapshot + change detection. Returns (new_added_tickers, inserted, removed)."""
    conn = get_conn()
    try:
        prev_tickers = set(_latest_snapshot_tickers(conn, "HSI"))
    finally:
        conn.close()

    index_updater_hk.update_hsi()

    conn = get_conn()
    try:
        curr_tickers = set(_latest_snapshot_tickers(conn, "HSI"))
    finally:
        conn.close()

    new_added = sorted(curr_tickers - prev_tickers)
    removed = len(prev_tickers - curr_tickers)
    return new_added, len(curr_tickers), removed


def list_active_tickers() -> list[str]:
    return get_index_tickers("HSI")


def backfill_new(new_tickers: list[str]) -> dict[str, str]:
    """Backfill = full HISTORY_YEARS_HK pull. Same code path as incremental
    because sync_log will be empty for these tickers."""
    if not new_tickers:
        return {}
    return stock_updater_hk.update_prices_batch(new_tickers)


def incremental(tickers: list[str]) -> dict[str, str]:
    if not tickers:
        return {}
    return stock_updater_hk.update_prices_batch(tickers)


def update_index_price() -> int:
    """Pull HSI ETF (2800.HK) daily close from akshare, write to index_prices."""
    last = query(
        "SELECT MAX(date) AS d FROM index_prices WHERE index_id=%s", ("HSI",)
    )
    last_date = last[0]["d"] if last and last[0]["d"] else None

    start = (last_date.strftime("%Y%m%d") if last_date else "20100101")
    end = date.today().strftime("%Y%m%d")

    try:
        raw = ak.stock_hk_hist(
            symbol="02800",
            period="daily",
            start_date=start,
            end_date=end,
            adjust="hfq",
        )
    except Exception as e:
        log.error(f"[HSI] ETF 拉取失败: {e}")
        return 0

    if raw is None or raw.empty:
        return 0

    rows = []
    for _, r in raw.iterrows():
        d = r["日期"]
        if hasattr(d, "date"):
            d = d.date()
        if last_date and d <= last_date:
            continue
        rows.append((d, "HSI", to_float(r.get("收盘"))))

    if not rows:
        return 0

    return execute(
        "INSERT IGNORE INTO index_prices (date, index_id, close) VALUES (%s,%s,%s)",
        rows, many=True,
    )


def rebase(tickers: Optional[list[str]] = None) -> dict[str, str]:
    """Full re-pull from START_DATE_HK for hfq rebase."""
    if tickers is None:
        tickers = list_active_tickers()
    return stock_updater_hk.update_prices_batch(tickers)


def _latest_snapshot_tickers(conn, index_id: str) -> list[str]:
    rows = query(
        """SELECT DISTINCT ticker FROM index_constituents
           WHERE index_id=%s AND snapshot_date = (
             SELECT MAX(snapshot_date) FROM index_constituents WHERE index_id=%s
           )""",
        (index_id, index_id),
    )
    return [r["ticker"] for r in rows]
