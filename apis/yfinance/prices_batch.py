"""Shared US equity batch orchestration for daily (1d) and weekly (1wk).

Public market entrypoints remain prices_us / prices_us_weekly — they build
UsPriceSpec at call time (so unittest.mock patches on those modules still work)
and call run_us_equity_batch. Never run daily+weekly in one call.
"""
from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Callable, Dict, List, Optional

import pandas as pd

from config import (
    HISTORY_YEARS_US,
    START_DATE_US,
    YF_BATCH_DELAY_BASE,
    YF_BATCH_DELAY_JITTER,
    YF_BATCH_SIZE,
    YF_LOOKBACK_DAYS,
    YF_RETRY_COUNT,
    YF_THREADS,
    YF_TIMEOUT,
)
from core.batch_utils import chunked
from core.db_client import get_conn
from core.http_utils import to_float, to_int
from modules.price_write import flush_prices_and_sync
from modules.sync_log import get_last_sync_map, set_sync_error
from apis.yfinance.client import download_with_retry
from apis.yfinance.normalize import normalize_daily_frame
from apis.yfinance.ticker_utils import to_yfinance_us

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class UsPriceSpec:
    label: str
    interval: str
    data_type: str
    price_table: str
    probe: Callable[[date], str]
    target_date: Callable[[], date]
    end_exclusive: Callable[[date], date]
    on_duplicate: bool
    support_years: bool


def price_rows_from_df(df: pd.DataFrame) -> list:
    return [
        (
            r.ticker,
            r.date,
            to_float(getattr(r, "open", None)),
            to_float(getattr(r, "high", None)),
            to_float(getattr(r, "low", None)),
            to_float(r.close),
            to_int(getattr(r, "volume", None)),
        )
        for r in df.itertuples(index=False)
    ]


def _sleep_between_batches(label: str) -> None:
    delay = YF_BATCH_DELAY_BASE + random.uniform(
        -YF_BATCH_DELAY_JITTER, YF_BATCH_DELAY_JITTER
    )
    log.debug(f"[{label}] 等待 {delay:.1f}s 后继续")
    time.sleep(delay)


def _download_and_save(
    conn,
    tickers: List[str],
    start_date: Optional[date],
    result: Dict[str, str],
    *,
    spec: UsPriceSpec,
    years: Optional[int] = None,
) -> None:
    if not tickers:
        return

    target = spec.target_date()
    if start_date is None:
        if spec.support_years and years:
            start_date = target - timedelta(days=365 * years)
        else:
            start_date = date.fromisoformat(START_DATE_US)

    end_dt = spec.end_exclusive(target)
    yf_symbols = [to_yfinance_us(t) for t in tickers]
    log.info(
        f"[{spec.label}] 下载 {len(tickers)} 只, {start_date} ~ {target} interval={spec.interval}"
    )

    try:
        df = download_with_retry(
            tickers=yf_symbols,
            start=start_date.strftime("%Y-%m-%d"),
            end=end_dt.strftime("%Y-%m-%d"),
            interval=spec.interval,
            threads=YF_THREADS,
            timeout=YF_TIMEOUT,
            retry_count=YF_RETRY_COUNT,
            repair=False,
            context=f"[{spec.label}] ",
        )
    except Exception as last_exc:
        msg = f"yfinance {spec.label} failed after {YF_RETRY_COUNT} retries: {last_exc}"
        log.error(msg)
        for t in tickers:
            set_sync_error(conn, t, spec.data_type, msg)
            result[t] = f"error: {last_exc}"
        return

    top_level: set = set()
    if df is not None and not df.empty and isinstance(df.columns, pd.MultiIndex):
        top_level = set(df.columns.get_level_values(0))

    price_rows: list = []
    sync_rows: list = []
    ok_tickers: list = []

    for t in tickers:
        yf_t = to_yfinance_us(t)
        if yf_t not in top_level:
            log.warning(f"[{t}] yfinance: ticker not in response")
            set_sync_error(conn, t, spec.data_type, "yfinance: ticker not in response")
            result[t] = "no_data"
            continue
        sub = df[yf_t]
        normalized = normalize_daily_frame(t, sub)
        if normalized.empty:
            log.warning(f"[{t}] yfinance: empty frame")
            set_sync_error(conn, t, spec.data_type, "yfinance: empty frame")
            result[t] = "no_data"
            continue
        rows = price_rows_from_df(normalized)
        new_last = normalized["date"].max()
        price_rows.extend(rows)
        sync_rows.append((t, spec.data_type, new_last, len(rows), "ok", ""))
        ok_tickers.append(t)
        result[t] = "ok"
        log.info(f"[{t}] 写入 {len(rows)} 条，最新={new_last}")

    if price_rows or sync_rows:
        try:
            flush_prices_and_sync(
                conn,
                price_rows,
                sync_rows,
                on_duplicate=spec.on_duplicate,
                price_table=spec.price_table,
            )
        except Exception as e:
            log.error(f"[{spec.label}] 写库失败: {e}")
            for t in ok_tickers:
                set_sync_error(conn, t, spec.data_type, str(e))
                result[t] = f"error: {e}"


def run_us_equity_batch(
    tickers: List[str],
    *,
    spec: UsPriceSpec,
    full_rebase: bool = False,
    years: Optional[int] = None,
) -> Dict[str, str]:
    if not tickers:
        return {}

    target = spec.target_date()
    status = spec.probe(target)

    if status == "rate_limit":
        log.warning(f"[AAPL {spec.label}] yfinance 被限速，跳过")
        return {t: "error: rate_limit" for t in tickers}
    if status == "no_data":
        log.warning(f"[AAPL {spec.label}] yfinance 暂无 {target} 数据，跳过")
        return {t: "error: no_data" for t in tickers}
    if status == "error":
        log.warning(f"[AAPL {spec.label}] 测试请求失败，跳过")
        return {t: "error: test_failed" for t in tickers}

    log.info(f"[AAPL {spec.label}] 已有 {target} 数据，开始批量下载")
    result: Dict[str, str] = {}
    conn = get_conn()
    try:
        if full_rebase:
            actual_years = years if (spec.support_years and years) else (
                HISTORY_YEARS_US if spec.support_years else None
            )
            log.info(f"[{spec.label}] rebase: {len(tickers)} tickers years={actual_years}")
            batches = list(chunked(tickers, YF_BATCH_SIZE))
            for idx, batch in enumerate(batches, 1):
                _download_and_save(
                    conn, batch, None, result, spec=spec, years=actual_years
                )
                if idx < len(batches):
                    _sleep_between_batches(spec.label)
        else:
            new_tickers: list[str] = []
            pending_tickers: list[str] = []
            pending_start: Optional[date] = None
            lookback_floor = target - timedelta(days=YF_LOOKBACK_DAYS)
            last_map = get_last_sync_map(conn, tickers, spec.data_type)
            for t in tickers:
                last = last_map.get(t)
                if last is None:
                    new_tickers.append(t)
                elif last < target:
                    start_dt = max(last + timedelta(days=1), lookback_floor)
                    pending_tickers.append(t)
                    if pending_start is None or start_dt < pending_start:
                        pending_start = start_dt

            if new_tickers:
                log.info(f"[{spec.label}] {len(new_tickers)} 新 ticker 全量")
                batches_new = list(chunked(new_tickers, YF_BATCH_SIZE))
                for idx, batch_new in enumerate(batches_new, 1):
                    _download_and_save(conn, batch_new, None, result, spec=spec)
                    if idx < len(batches_new):
                        _sleep_between_batches(spec.label)

            if pending_tickers:
                log.info(
                    f"[{spec.label}] {len(pending_tickers)} 增量 "
                    f"from {pending_start} to {target}"
                )
                batches_pending = list(chunked(pending_tickers, YF_BATCH_SIZE))
                for idx, batch_pending in enumerate(batches_pending, 1):
                    _download_and_save(
                        conn, batch_pending, pending_start, result, spec=spec
                    )
                    if idx < len(batches_pending):
                        _sleep_between_batches(spec.label)
            else:
                log.info(f"[{spec.label}] 全部已同步到 {target}")

        return result
    finally:
        conn.close()
