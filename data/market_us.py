"""US market module: thin adapter exposing the MarketModule protocol.

Wraps existing index_updater_us.update_sp500() and stock_updater_us.update_prices_batch()
into the Pipeline contract.

支持指数：
- SP500（S&P 500，约503支）
- RUSSELL1000（Russell 1000，约1008支）
- 默认组合：SP500 + RUSSELL1000（约1016支）
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Optional

import yfinance as yf

from db import get_conn, get_index_tickers, get_latest_snapshot_tickers, query, execute
from data import index_updater_us
from data import index_updater_russell1000
from data import stock_updater_us
from data.base import to_float

log = logging.getLogger(__name__)

market_id = "us"


def update_index() -> tuple[list[str], int, int]:
    """Run SP500 + Russell1000 snapshot + change detection.

    Returns:
        (new_added_tickers, total_inserted_rows, removed_count)
    """
    # SP500
    prev_sp500 = set(get_latest_snapshot_tickers("SP500"))
    index_updater_us.update_sp500()
    curr_sp500 = set(get_latest_snapshot_tickers("SP500"))
    sp500_new = sorted(curr_sp500 - prev_sp500)
    sp500_removed = len(prev_sp500 - curr_sp500)

    # Russell 1000
    prev_r1k = set(get_latest_snapshot_tickers("RUSSELL1000"))
    index_updater_russell1000.update_russell1000()
    curr_r1k = set(get_latest_snapshot_tickers("RUSSELL1000"))
    r1k_new = sorted(curr_r1k - prev_r1k)
    r1k_removed = len(prev_r1k - curr_r1k)

    # 合并新增
    all_new = sorted(set(sp500_new) | set(r1k_new))
    total_inserted = len(curr_sp500) + len(curr_r1k)
    total_removed = sp500_removed + r1k_removed

    return all_new, total_inserted, total_removed


def list_active_tickers(index: Optional[str] = None) -> list[str]:
    """返回美股 ticker 列表。

    Args:
        index: 指定指数（SP500/RUSSELL1000），None 返回组合（SP500+R1000）

    Returns:
        ticker 列表
    """
    if index == "SP500":
        return get_index_tickers("SP500")
    if index == "RUSSELL1000":
        return get_index_tickers("RUSSELL1000")

    # 默认：SP500 + Russell 1000 组合（约1016支）
    sp500 = get_index_tickers("SP500")
    r1k = get_index_tickers("RUSSELL1000")
    combined = sorted(set(sp500) | set(r1k))
    return combined


def backfill_new(new_tickers: list[str]) -> dict[str, str]:
    """Backfill = full HISTORY_YEARS_US pull. Same code path as incremental
    because sync_log will be empty for these tickers."""
    if not new_tickers:
        return {}
    return stock_updater_us.update_prices_batch(new_tickers)


def incremental(tickers: list[str]) -> dict[str, str]:
    if not tickers:
        return {}
    return stock_updater_us.update_prices_batch(tickers)


def update_index_price() -> int:
    """Pull ^GSPC, ^RUT, and 11 sector ETFs daily close from yfinance, write to index_prices."""
    indices = [
        ("^GSPC", "SP500"),
        ("^RUT", "RUSSELL1000"),
        ("XLK", "XLK"),
        ("XLY", "XLY"),
        ("XLF", "XLF"),
        ("XLV", "XLV"),
        ("XLP", "XLP"),
        ("XLI", "XLI"),
        ("XLE", "XLE"),
        ("XLB", "XLB"),
        ("XLRE", "XLRE"),
        ("XLU", "XLU"),
        ("XLC", "XLC"),
    ]
    total = 0
    for symbol, index_id in indices:
        last = query(
            "SELECT MAX(date) AS d FROM index_prices WHERE index_id=%s", (index_id,)
        )
        last_date = last[0]["d"] if last and last[0]["d"] else None

        start = last_date.isoformat() if last_date else "2010-01-01"
        df = yf.download(symbol, start=start, interval="1d",
                         auto_adjust=False, actions=False, progress=False)
        if df.empty:
            continue

        df = df.reset_index()
        df.columns = [str(c).lower() if not isinstance(c, tuple) else str(c[0]).lower() for c in df.columns]
        rows = []
        for _, r in df.iterrows():
            d = r["date"].date() if hasattr(r["date"], "date") else r["date"]
            if last_date and d <= last_date:
                continue
            rows.append((d, index_id, to_float(r.get("close"))))

        if not rows:
            continue

        total += execute(
            "INSERT IGNORE INTO index_prices (date, index_id, close) VALUES (%s,%s,%s)",
            rows, many=True
        )
    return total


def rebase(tickers: Optional[list[str]] = None, years: Optional[int] = None, index: Optional[str] = None) -> dict[str, str]:
    """US rebase: full re-pull from specified years (raw prices, no hfq)."""
    targets = tickers if tickers else list_active_tickers(index=index)
    return stock_updater_us.update_prices_batch(targets, full_rebase=True, years=years)
