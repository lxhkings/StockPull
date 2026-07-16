"""Shared CN equity batch orchestration for daily (D) and weekly (W).

Public market entrypoints remain prices_cn / prices_cn_weekly — they build
CnPriceSpec at call time and call run_cn_equity_batch.
Never run daily+weekly in one call.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple

import pandas as pd
from tqdm import tqdm

from config import TUSHARE_BACKFILL_START
from core.db_client import get_conn
from core.http_utils import to_float, to_int
from core.trading_calendar import last_cn_trading_date
from modules.price_write import flush_prices_and_sync
from modules.sync_log import get_last_sync_map
from apis.tushare.client import get_client

log = logging.getLogger(__name__)

BATCH_COMMIT_SIZE = 50  # 每50个ticker commit一次，减少网络往返


@dataclass(frozen=True)
class CnPriceSpec:
    label: str
    freq: str  # "D" | "W"
    data_type: str
    price_table: str
    on_duplicate: bool = True


def normalize_pro_bar(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    out = pd.DataFrame({
        "date": pd.to_datetime(df["trade_date"], format="%Y%m%d").dt.date,
        "open": df["open"].apply(to_float),
        "high": df["high"].apply(to_float),
        "low": df["low"].apply(to_float),
        "close": df["close"].apply(to_float),
        "volume": df["vol"].apply(to_int),
    })
    return out.sort_values("date").reset_index(drop=True)


def _cn_history_start(last_trading: date, years: Optional[int]) -> str:
    """Full-history window start (YYYYMMDD). Shared by fetch path and logs."""
    if years:
        return (last_trading - timedelta(days=365 * years)).strftime("%Y%m%d")
    return TUSHARE_BACKFILL_START


def _price_rows_from_normalized(ticker: str, df: pd.DataFrame) -> List[Tuple]:
    """Build DB rows from normalize_pro_bar output (no second to_float)."""
    return [
        (ticker, r.date, r.open, r.high, r.low, r.close, r.volume)
        for r in df.itertuples(index=False)
    ]


def _fetch_one(client, ticker: str, start: str, end: str, freq: str) -> pd.DataFrame:
    """tushare pro_bar 单 ticker 拉取。start/end 格式 YYYYMMDD。"""
    df_raw = client.pro_bar(
        ts_code=ticker, adj="qfq", start_date=start, end_date=end, freq=freq,
    )
    return normalize_pro_bar(df_raw)


def _flush_batch(
    conn,
    prices_buf: List[Tuple],
    sync_buf: List[Tuple],
    *,
    spec: CnPriceSpec,
) -> None:
    """批量 commit prices + sync_log。"""
    flush_prices_and_sync(
        conn,
        prices_buf,
        sync_buf,
        on_duplicate=spec.on_duplicate,
        price_table=spec.price_table,
    )


def _process_tickers_batched(
    conn,
    client,
    tickers: List[str],
    last_trading: date,
    full_rebase: bool,
    result: Dict[str, str],
    *,
    spec: CnPriceSpec,
    last_map: Dict[str, Optional[date]],
    progress_label: str = "补缺",
    years: Optional[int] = None,
) -> Tuple[List[Tuple], List[Tuple]]:
    """批量处理 ticker，返回未 flush 的 buffer。

    增量时用调用方传入的 last_map，禁止循环内 get_last_sync。
    """
    prices_buf: List[Tuple] = []
    sync_buf: List[Tuple] = []

    for t in tqdm(tickers, desc=f"[{spec.label}] {progress_label}", unit="ticker"):
        try:
            if full_rebase:
                start = _cn_history_start(last_trading, years)
            else:
                last = last_map.get(t)
                if last:
                    start = (last + timedelta(days=1)).strftime("%Y%m%d")
                else:
                    start = TUSHARE_BACKFILL_START
            end = last_trading.strftime("%Y%m%d")

            df = _fetch_one(client, t, start, end, spec.freq)
            if df.empty:
                # 节假日无数据是正常的，只有当天缺失才记 error
                if end == date.today().strftime("%Y%m%d"):
                    sync_buf.append(
                        (t, spec.data_type, date.today(), 0, "error", "tushare: no data")
                    )
                    result[t] = "no_data"
                else:
                    result[t] = "skip"
                if len(sync_buf) >= BATCH_COMMIT_SIZE:
                    _flush_batch(conn, prices_buf, sync_buf, spec=spec)
                    prices_buf.clear()
                    sync_buf.clear()
                continue

            prices_buf.extend(_price_rows_from_normalized(t, df))
            new_last = df["date"].max()
            rows_count = len(df)
            sync_buf.append((t, spec.data_type, new_last, rows_count, "ok", ""))
            result[t] = "ok"

            if len(sync_buf) >= BATCH_COMMIT_SIZE:
                _flush_batch(conn, prices_buf, sync_buf, spec=spec)
                prices_buf.clear()
                sync_buf.clear()

        except Exception as e:
            _flush_batch(conn, prices_buf, sync_buf, spec=spec)
            prices_buf.clear()
            sync_buf.clear()
            sync_buf.append((t, spec.data_type, date.today(), 0, "error", str(e)[:500]))
            _flush_batch(conn, [], sync_buf, spec=spec)
            sync_buf.clear()
            log.error(f"[{t}] {progress_label}失败: {e}")
            result[t] = f"error: {e}"

    return prices_buf, sync_buf


def run_cn_equity_batch(
    tickers: List[str],
    *,
    spec: CnPriceSpec,
    full_rebase: bool = False,
    years: Optional[int] = None,
) -> Dict[str, str]:
    """批量增量/回填 CN 日线或周线。

    Args:
      tickers: canonical A-share tickers (e.g., 600519.SH)
      spec: freq / data_type / price_table 等
      full_rebase: if True, ignore sync_log and pull from TUSHARE_BACKFILL_START
      years: 指定历史年数（None 时使用 TUSHARE_BACKFILL_START）

    Returns: {ticker: status}
    """
    if not tickers:
        return {}

    last_trading = last_cn_trading_date()
    result: Dict[str, str] = {}

    conn = get_conn()
    try:
        client = get_client()
        new_tickers: List[str] = []
        pending_tickers: List[str] = []

        last_map: Dict[str, Optional[date]] = (
            {} if full_rebase else get_last_sync_map(conn, tickers, spec.data_type)
        )
        for t in tickers:
            if full_rebase:
                pending_tickers.append(t)
                continue
            last = last_map.get(t)
            if last is None:
                new_tickers.append(t)
            elif last < last_trading:
                pending_tickers.append(t)

        log.info(
            f"[{spec.label}] 总数={len(tickers)}, "
            f"new={len(new_tickers)}, pending={len(pending_tickers)}"
        )

        if new_tickers:
            # new 路径内部 full_rebase=True：与 CLI rebase 不同，仅表示忽略
            # sync_log、从 backfill 起点拉全量（见 _process_tickers_batched）。
            start_disp = _cn_history_start(last_trading, years)
            log.info(
                f"[{spec.label}] {len(new_tickers)} 新ticker需回填 "
                f"from {start_disp}"
            )
            buf_p, buf_s = _process_tickers_batched(
                conn, client, new_tickers, last_trading,
                full_rebase=True, result=result,
                spec=spec, last_map=last_map,
                progress_label="回填", years=years,
            )
            _flush_batch(conn, buf_p, buf_s, spec=spec)

        if pending_tickers:
            log.info(f"[{spec.label}] {len(pending_tickers)} ticker需增量补缺")
            buf_p, buf_s = _process_tickers_batched(
                conn, client, pending_tickers, last_trading,
                full_rebase=full_rebase, result=result,
                spec=spec, last_map=last_map,
                progress_label="补缺" if not full_rebase else "回填",
                years=years if full_rebase else None,
            )
            _flush_batch(conn, buf_p, buf_s, spec=spec)

        if not new_tickers and not pending_tickers:
            log.info(f"[{spec.label}] 所有ticker已同步到 {last_trading}")

        return result
    finally:
        conn.close()
