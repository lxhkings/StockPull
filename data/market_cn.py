"""A-share market module: 全量A股 via tushare stock_basic."""

from __future__ import annotations

import logging
from typing import Optional

import pandas as pd

from core.db_client import get_conn, query, execute
from ts_ingest import prices_cn as stock_updater_cn
from core.http_utils import to_float
from ts_ingest.backfill_lists import backfill_stocks_a
from ts_ingest.client import get_client
from ts_ingest.ticker_map import index_id_to_ts_code

log = logging.getLogger(__name__)

market_id = "cn"


def update_index() -> tuple[list[str], int, int]:
    """更新全量A股列表（从tushare stock_basic）。"""
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM stocks "
            "WHERE ticker LIKE '%%.SH' OR ticker LIKE '%%.SZ' OR ticker LIKE '%%.BJ'"
        )
        prev_count = cur.fetchone()[0]
    finally:
        conn.close()

    inserted = backfill_stocks_a()

    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM stocks "
            "WHERE ticker LIKE '%%.SH' OR ticker LIKE '%%.SZ' OR ticker LIKE '%%.BJ'"
        )
        curr_count = cur.fetchone()[0]
    finally:
        conn.close()

    added = curr_count - prev_count
    log.info(f"[cn] stocks表更新: prev={prev_count}, curr={curr_count}, added={added}")
    # new_tickers返回空，因为list_active_tickers直接读stocks表
    return [], inserted, 0


def list_active_tickers(index: str | None = None) -> list[str]:
    """Return active tickers. ``index`` is ignored (CN/HK single-universe)."""
    rows = query(
        "SELECT ticker FROM stocks "
        "WHERE ticker LIKE '%%.SH' OR ticker LIKE '%%.SZ' OR ticker LIKE '%%.BJ' "
        "ORDER BY ticker"
    )
    return [r["ticker"] for r in rows]


def backfill_new(new_tickers: list[str]) -> dict[str, str]:
    if not new_tickers:
        return {}
    return stock_updater_cn.update_prices_batch(new_tickers)


def incremental(tickers: list[str]) -> dict[str, str]:
    if not tickers:
        return {}
    return stock_updater_cn.update_prices_batch(tickers)


def update_index_price() -> int:
    """中证800 指数 close via tushare index_daily + 行业 ETF hfq close via fund_daily × fund_adj。"""
    csi800_count = _update_csi800()
    from ts_ingest.etf_cn import update_etf_prices
    etf_count = update_etf_prices()
    return csi800_count + etf_count


def _update_csi800() -> int:
    """中证800 指数 close via tushare index_daily (000906.SH)。"""
    last = query(
        "SELECT MAX(date) AS d FROM index_prices WHERE index_id=%s", ("CSI800",)
    )
    last_date = last[0]["d"] if last and last[0]["d"] else None

    client = get_client()
    ts_code = index_id_to_ts_code("CSI800")

    try:
        start_date = last_date.strftime("%Y%m%d") if last_date else None
        raw = client.call("index_daily", ts_code=ts_code, start_date=start_date)

        if raw is None or raw.empty:
            return 0

        required_cols = {"trade_date", "close"}
        if not required_cols.issubset(raw.columns):
            log.error(f"[CSI800] index_daily missing columns: {required_cols - set(raw.columns)}")
            return 0

        df = pd.DataFrame({
            "date":  pd.to_datetime(raw["trade_date"]).dt.date,
            "close": raw["close"].astype(float),
        })

        if last_date:
            df = df[df["date"] > last_date]

        if df.empty:
            return 0

        rows = [(r.date, "CSI800", to_float(r.close)) for r in df.itertuples(index=False)]
        return execute(
            "INSERT IGNORE INTO index_prices (date, index_id, close) VALUES (%s,%s,%s)",
            rows, many=True,
        )
    except Exception as e:
        log.error(f"[CSI800] index_daily failed: {e}")
        return 0


def rebase(
    tickers: Optional[list[str]] = None,
    years: Optional[int] = None,
    index: str | None = None,
) -> dict[str, str]:
    """Full re-pull from START_DATE_CN to fix qfq drift. ``index`` is ignored (CN single-universe)."""
    targets = tickers if tickers else list_active_tickers()
    return stock_updater_cn.update_prices_batch(targets, full_rebase=True, years=years)


def weekly(tickers: list[str] | None = None) -> dict[str, str]:
    """Pull weekly prices for CN universe into prices_weekly."""
    from ts_ingest import prices_cn_weekly
    targets = tickers or list_active_tickers()
    return prices_cn_weekly.update_weekly_batch(targets)
