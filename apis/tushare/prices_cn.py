"""A-share daily-K updater via Tushare (pre-adjusted, qfq).

参考 stock_updater_us.py 补缺逻辑：
- 判断哪些ticker需要更新
- 只拉缺失日期，不重复拉已同步数据
- 批量commit减少NAS网络往返（每BATCH_COMMIT_SIZE个ticker一次）
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Dict, List, Tuple, Optional

import pandas as pd
from tqdm import tqdm

from config import HISTORY_YEARS_CN, TUSHARE_BACKFILL_START
from core.db_client import get_conn
from modules.sync_log import get_last_sync, get_last_sync_map
from modules.price_write import flush_prices_and_sync
from core.http_utils import to_float, to_int
from core.trading_calendar import last_cn_trading_date
from apis.tushare.client import get_client

log = logging.getLogger(__name__)

SYNC_DATA_TYPE = "price"
BATCH_COMMIT_SIZE = 50  # 每50个ticker commit一次，减少网络往返


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


def _flush_batch(conn, prices_buf: List[Tuple], sync_buf: List[Tuple]):
    """批量commit prices + sync_log。"""
    flush_prices_and_sync(conn, prices_buf, sync_buf, on_duplicate=True)


def _process_tickers_batched(
    conn, tickers: List[str], last_trading: date,
    full_rebase: bool, result: Dict[str, str],
    progress_label: str = "补缺",
    years: Optional[int] = None
) -> Tuple[List[Tuple], List[Tuple]]:
    """批量处理ticker，返回未flush的buffer。"""
    prices_buf: List[Tuple] = []
    sync_buf: List[Tuple] = []

    for t in tqdm(tickers, desc=f"[cn] {progress_label}", unit="ticker"):
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

    last_trading = last_cn_trading_date()
    result: Dict[str, str] = {}

    conn = get_conn()
    try:
        new_tickers = []
        pending_tickers = []

        last_map = {} if full_rebase else get_last_sync_map(conn, tickers, SYNC_DATA_TYPE)
        for t in tickers:
            if full_rebase:
                pending_tickers.append(t)
                continue
            last = last_map.get(t)
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