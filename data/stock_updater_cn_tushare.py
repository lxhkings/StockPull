"""A-share daily-K updater via Tushare (pre-adjusted, qfq).

参考 stock_updater_us.py 补缺逻辑：
- 判断哪些ticker需要更新
- 只拉缺失日期，不重复拉已同步数据
- 批量commit减少NAS网络往返（每BATCH_COMMIT_SIZE个ticker一次）
"""
from __future__ import annotations

import logging
import time
from datetime import date, datetime, timedelta
from typing import Dict, List, Tuple, Optional

import pandas as pd

from config import HISTORY_YEARS_CN, START_DATE_CN, TUSHARE_BACKFILL_START
from db import get_conn, get_last_sync
from core.http_utils import to_float, to_int
from core.progress import log_progress
from ts_ingest.client import get_client

log = logging.getLogger(__name__)

SYNC_DATA_TYPE = "price"
BATCH_COMMIT_SIZE = 50  # 每50个ticker commit一次，减少网络往返


def _last_cn_trading_date() -> date:
    """北京时间视角下A股最近已收盘交易日。

    A股15:00收盘，tushare数据16:00入库完成。
    """
    now = datetime.now()
    weekday = now.weekday()  # 0=周一, 5=周六, 6=周日
    hour = now.hour

    # 周六：周五（周五数据周六早上入库）
    if weekday == 5:
        return (now - timedelta(days=1)).date()

    # 周日：周五
    if weekday == 6:
        return (now - timedelta(days=2)).date()

    # 周一16点前：周五
    if weekday == 0 and hour < 16:
        return (now - timedelta(days=3)).date()

    # 其他交易日：
    # 16点后 → 当天数据已入库，取当天
    # 16点前 → 等待当天入库，取前一天
    if hour >= 16:
        return now.date()
    return (now - timedelta(days=1)).date()


def _normalize_pro_bar(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    out = pd.DataFrame({
        "date": pd.to_datetime(df["trade_date"], format="%Y%m%d").dt.date,
        "open": df["open"].apply(to_float),
        "high": df["high"].apply(to_float),
        "low":  df["low"].apply(to_float),
        "close": df["close"].apply(to_float),
        "volume": df["vol"].apply(to_int),
    })
    return out.sort_values("date").reset_index(drop=True)


def _fetch_one(ticker: str, start: str, end: str) -> pd.DataFrame:
    """tushare pro_bar 单ticker拉取。start/end格式YYYYMMDD。"""
    client = get_client()
    df_raw = client.pro_bar(ts_code=ticker, adj="qfq", start_date=start, end_date=end, freq="D")
    return _normalize_pro_bar(df_raw)


def _save_prices_batch(conn, rows: List[Tuple]) -> int:
    """批量写入prices表，不commit（由调用者控制）。"""
    sql = """
        INSERT INTO prices (ticker, date, open, high, low, close, volume)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            open=VALUES(open), high=VALUES(high), low=VALUES(low),
            close=VALUES(close), volume=VALUES(volume)
    """
    with conn.cursor() as cur:
        cur.executemany(sql, rows)
    return len(rows)


def _flush_batch(conn, prices_buf: List[Tuple], sync_buf: List[Tuple]):
    """批量commit prices + sync_log。"""
    if prices_buf:
        _save_prices_batch(conn, prices_buf)
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
    years: Optional[int] = None
) -> Tuple[List[Tuple], List[Tuple]]:
    """批量处理ticker，返回未flush的buffer。"""
    prices_buf: List[Tuple] = []
    sync_buf: List[Tuple] = []
    t0 = time.monotonic()

    for i, t in enumerate(tickers, 1):
        try:
            if full_rebase:
                if years:
                    # 根据指定的年数计算起始日期
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
                # 节假日无数据是正常的，只有当天缺失才记error
                if end == date.today().strftime("%Y%m%d"):
                    sync_buf.append((t, SYNC_DATA_TYPE, date.today(), 0, "error", "tushare: no data"))
                    result[t] = "no_data"
                else:
                    # 历史日期无数据（节假日），正常skip
                    result[t] = "skip"
                if len(sync_buf) >= BATCH_COMMIT_SIZE:
                    _flush_batch(conn, prices_buf, sync_buf)
                    prices_buf.clear()
                    sync_buf.clear()
                continue

            # 累积prices rows
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

            # 达到batch size时flush
            if len(sync_buf) >= BATCH_COMMIT_SIZE:
                _flush_batch(conn, prices_buf, sync_buf)
                log_progress(i, len(tickers), t0, every=1,
                             context=f"[cn] {progress_label}进度 ", extra="(batch flush)")
                prices_buf.clear()
                sync_buf.clear()

        except Exception as e:
            # 出错时先flush已累积的数据，保证已成功的不丢失
            _flush_batch(conn, prices_buf, sync_buf)
            prices_buf.clear()
            sync_buf.clear()
            # 记录错误
            sync_buf.append((t, SYNC_DATA_TYPE, date.today(), 0, "error", str(e)[:500]))
            _flush_batch(conn, [], sync_buf)
            sync_buf.clear()
            log.error(f"[{t}] {progress_label}失败: {e}")
            result[t] = f"error: {e}"

        if len(sync_buf) < BATCH_COMMIT_SIZE:
            log_progress(i, len(tickers), t0, every=100, context=f"[cn] {progress_label}进度 ")

    return prices_buf, sync_buf


def update_prices_batch(tickers: List[str], full_rebase: bool = False, years: Optional[int] = None) -> Dict[str, str]:
    """批量增量拉取，参考US补缺逻辑。

    Args:
      tickers: canonical A-share tickers (e.g., 600519.SH)
      full_rebase: if True, ignore sync_log and pull from START_DATE_CN
      years: 指定历史年数（None 时使用 START_DATE_CN）

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

        log.info(f"[cn] 总数={len(tickers)}, new={len(new_tickers)}, pending={len(pending_tickers)}")

        # 新ticker回填（批量）
        if new_tickers:
            log.info(f"[cn] {len(new_tickers)} 新ticker需回填 {HISTORY_YEARS_CN} 年历史")
            buf_p, buf_s = _process_tickers_batched(
                conn, new_tickers, last_trading,
                full_rebase=True, result=result,
                progress_label="回填", years=years
            )
            _flush_batch(conn, buf_p, buf_s)

        # pending ticker增量补缺（批量）
        if pending_tickers:
            log.info(f"[cn] {len(pending_tickers)} ticker需增量补缺")
            buf_p, buf_s = _process_tickers_batched(
                conn, pending_tickers, last_trading,
                full_rebase=full_rebase, result=result,
                progress_label="补缺" if not full_rebase else "回填",
                years=years if full_rebase else None
            )
            _flush_batch(conn, buf_p, buf_s)

        if not new_tickers and not pending_tickers:
            log.info(f"[cn] 所有ticker已同步到 {last_trading}")

        return result
    finally:
        conn.close()