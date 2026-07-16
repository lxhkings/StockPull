"""A-share weekly-K updater via Tushare (pre-adjusted, qfq).

Thin entry: builds CnPriceSpec and delegates to run_cn_equity_batch.
保留 _normalize_pro_bar / _save_weekly_prices_batch / SYNC_DATA_TYPE 供单测。
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from apis.tushare.prices_cn_batch import (
    CnPriceSpec,
    normalize_pro_bar,
    run_cn_equity_batch,
)

SYNC_DATA_TYPE = "price_weekly"


def _normalize_pro_bar(df):
    return normalize_pro_bar(df)


def _save_weekly_prices_batch(conn, rows: List[Tuple]) -> int:
    """Kept for unit test table-name assertion."""
    sql = """
        INSERT INTO prices_weekly (ticker, date, open, high, low, close, volume)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            open=VALUES(open), high=VALUES(high), low=VALUES(low),
            close=VALUES(close), volume=VALUES(volume)
    """
    with conn.cursor() as cur:
        cur.executemany(sql, rows)
    return len(rows)


def update_weekly_batch(
    tickers: List[str],
    full_rebase: bool = False,
    years: Optional[int] = None,
) -> Dict[str, str]:
    """批量增量拉取A股周线，写入 prices_weekly 表。

    Args:
      tickers: canonical A-share tickers (e.g., 600519.SH)
      full_rebase: if True, ignore sync_log and pull from TUSHARE_BACKFILL_START
      years: 指定历史年数（None 时使用 TUSHARE_BACKFILL_START）

    Returns: {ticker: status}
    """
    spec = CnPriceSpec(
        label="cn weekly",
        freq="W",
        data_type="price_weekly",
        price_table="prices_weekly",
        on_duplicate=True,
    )
    return run_cn_equity_batch(
        tickers, spec=spec, full_rebase=full_rebase, years=years
    )
