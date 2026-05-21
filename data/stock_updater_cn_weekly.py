# data/stock_updater_cn_weekly.py
"""A-share weekly-K updater via Tushare (pre-adjusted, qfq).

与 stock_updater_cn_tushare.py 完全对称，差异：
- pro_bar(freq="W") 拉取周线
- 写入 prices_weekly 表
- sync_log data_type = "price_weekly"
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Dict, List, Tuple, Optional

import pandas as pd

from config import TUSHARE_BACKFILL_START
from db import get_conn, get_last_sync
from data.base import to_float, to_int
from data.stock_updater_cn_tushare import _last_cn_trading_date
from ts_ingest.client import get_client

log = logging.getLogger(__name__)

SYNC_DATA_TYPE = "price_weekly"
BATCH_COMMIT_SIZE = 50


def _normalize_pro_bar(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    out = pd.DataFrame({
        "date":   pd.to_datetime(df["trade_date"], format="%Y%m%d").dt.date,
        "open":   df["open"].apply(to_float),
        "high":   df["high"].apply(to_float),
        "low":    df["low"].apply(to_float),
        "close":  df["close"].apply(to_float),
        "volume": df["vol"].apply(to_int),
    })
    return out.sort_values("date").reset_index(drop=True)


def _fetch_one(ticker: str, start: str, end: str) -> pd.DataFrame:
    """tushare pro_bar 单ticker周线拉取。start/end格式YYYYMMDD。"""
    client = get_client()
    df_raw = client.pro_bar(ts_code=ticker, adj="qfq", start_date=start, end_date=end, freq="W")
    return _normalize_pro_bar(df_raw)


def _save_weekly_prices_batch(conn, rows: List[Tuple]) -> int:
    """批量写入prices_weekly表，不commit（由调用者控制）。"""
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


def _flush_batch(conn, prices_buf: List[Tuple], sync_buf: List[Tuple]):
    """批量commit prices_weekly + sync_log。"""
    if prices_buf:
        _save_weekly_prices_batch(conn, prices_buf)
    if sync_buf:
        sql = """
            INSERT INTO sync_log
              (ticker, data_type, last_date, rows_added, status, message)
            VALUES (%s,%s,%s,%s,%s,%s)
            ON DUPLICATE KEY UPDATE
              last_date  = IF(VALUES(status)='ok', VALUES(last_date), last_date),
              rows_added = VALUES(rows_added),
              last_run   = CURRENT_TIMESTAMP,
              status     = VALUES(status),
              message    = VALUES(message)
        """
        with conn.cursor() as cur:
            cur.executemany(sql, sync_buf)
    conn.commit()


def _process_tickers_batched(
    conn, tickers: List[str], last_trading: date,
    full_rebase: bool, result: Dict[str, str],
    progress_label: str = "补缺",
    years: Optional[int] = None,
) -> Tuple[List[Tuple], List[Tuple]]:
    """批量处理ticker，返回未flush的buffer。"""
    prices_buf: List[Tuple] = []
    sync_buf: List[Tuple] = []

    for i, t in enumerate(tickers, 1):
        try:
            if full_rebase:
                if years:
                    start_date = last_trading - timedelta(days=365 * years)
                    start = start_date.strftime("%Y%m%d")
                else:
                    start = TUSHARE_BACKFILL_START
            else:
                last = get_last_sync(conn, t, SYNC_DATA_TYPE)
                if last:
                    start = (last + timedelta(days=1)).strftime("%Y%m%d")
                else:
                    start = TUSHARE_BACKFILL_START
            end = last_trading.strftime("%Y%m%d")

            df = _fetch_one(t, start, end)
            if df.empty:
                if end == date.today().strftime("%Y%m%d"):
                    sync_buf.append((t, SYNC_DATA_TYPE, date.today(), 0, "error", "tushare: no data"))
                    result[t] = "no_data"
                else:
                    result[t] = "skip"
                if len(sync_buf) >= BATCH_COMMIT_SIZE:
                    _flush_batch(conn, prices_buf, sync_buf)
                    prices_buf.clear()
                    sync_buf.clear()
                continue

            for _, r in df.iterrows():
                prices_buf.append((
                    t, r["date"],
                    to_float(r["open"]), to_float(r["high"]),
                    to_float(r["low"]), to_float(r["close"]),
                    to_int(r["volume"]),
                ))
            new_last = df["date"].max()
            rows_count = len(df)
            sync_buf.append((t, SYNC_DATA_TYPE, new_last, rows_count, "ok", ""))
            result[t] = "ok"

            if len(sync_buf) >= BATCH_COMMIT_SIZE:
                _flush_batch(conn, prices_buf, sync_buf)
                log.info(f"[cn weekly] {progress_label}进度 {i}/{len(tickers)} (batch flush)")
                prices_buf.clear()
                sync_buf.clear()

        except Exception as e:
            _flush_batch(conn, prices_buf, sync_buf)
            prices_buf.clear()
            sync_buf.clear()
            sync_buf.append((t, SYNC_DATA_TYPE, date.today(), 0, "error", str(e)[:500]))
            _flush_batch(conn, [], sync_buf)
            sync_buf.clear()
            log.error(f"[{t}] {progress_label}失败: {e}")
            result[t] = f"error: {e}"

        if i % 100 == 0 and len(sync_buf) < BATCH_COMMIT_SIZE:
            log.info(f"[cn weekly] {progress_label}进度 {i}/{len(tickers)}")

    return prices_buf, sync_buf


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
    if not tickers:
        return {}

    last_trading = _last_cn_trading_date()
    result: Dict[str, str] = {}

    conn = get_conn()
    try:
        new_tickers = []
        pending_tickers = []

        for t in tickers:
            if full_rebase:
                pending_tickers.append(t)
                continue
            last = get_last_sync(conn, t, SYNC_DATA_TYPE)
            if last is None:
                new_tickers.append(t)
            elif last < last_trading:
                pending_tickers.append(t)

        log.info(f"[cn weekly] 总数={len(tickers)}, new={len(new_tickers)}, pending={len(pending_tickers)}")

        if new_tickers:
            log.info(f"[cn weekly] {len(new_tickers)} 新ticker需回填历史")
            buf_p, buf_s = _process_tickers_batched(
                conn, new_tickers, last_trading,
                full_rebase=True, result=result,
                progress_label="回填", years=years,
            )
            _flush_batch(conn, buf_p, buf_s)

        if pending_tickers:
            log.info(f"[cn weekly] {len(pending_tickers)} ticker需增量补缺")
            buf_p, buf_s = _process_tickers_batched(
                conn, pending_tickers, last_trading,
                full_rebase=full_rebase, result=result,
                progress_label="补缺" if not full_rebase else "回填",
                years=years if full_rebase else None,
            )
            _flush_batch(conn, buf_p, buf_s)

        if not new_tickers and not pending_tickers:
            log.info(f"[cn weekly] 所有ticker已同步到 {last_trading}")

        return result
    finally:
        conn.close()
