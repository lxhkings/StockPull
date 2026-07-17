"""US equity intraday batch orchestration (15m / 1h).

Public entry remains prices_intraday.update_intraday — it builds IntradaySpec
and calls run_intraday_batch. Does not share UsPriceSpec / run_us_equity_batch
(different table schema, sync keys, and solo-fallback behavior).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Dict, List, Optional

import pandas as pd
import pymysql.err

from config import YF_BATCH_SIZE, YF_RETRY_COUNT, YF_TIMEOUT
from core.batch_utils import chunked
from core.db_client import get_conn
from core.http_utils import to_float, to_int
from modules.db_admin import get_index_tickers
from modules.sync_log import get_last_sync_map, set_sync_error, set_sync_ok
from apis.yfinance.batch_delay import sleep_between_batches
from apis.yfinance.client import download_with_retry
from apis.yfinance.normalize import normalize_intraday_frame
from apis.yfinance.probe import (
    INTERVAL_LOOKBACK_DAYS,
    YF_INTERVAL_MAP,
    probe_intraday,
)
from apis.yfinance.ticker_utils import to_yfinance_us

log = logging.getLogger(__name__)

SUPPORTED_INTERVALS = list(YF_INTERVAL_MAP.keys())


@dataclass(frozen=True)
class IntradaySpec:
    interval: str  # user-facing: 15m / 1h
    yf_interval: str  # yfinance: 15m / 60m
    data_type: str  # sync_log: intraday_15m / intraday_60m
    lookback_days: int
    label: str


def build_intraday_spec(interval: str) -> IntradaySpec:
    if interval not in SUPPORTED_INTERVALS:
        raise ValueError(
            f"Unsupported interval: {interval}. Supported: {SUPPORTED_INTERVALS}"
        )
    yf_ivl = YF_INTERVAL_MAP[interval]
    return IntradaySpec(
        interval=interval,
        yf_interval=yf_ivl,
        data_type=f"intraday_{yf_ivl}",
        lookback_days=INTERVAL_LOOKBACK_DAYS[interval],
        label=f"intraday {interval}",
    )


def sync_type(interval: str) -> str:
    """'15m' → 'intraday_15m', '1h' → 'intraday_60m'"""
    return f"intraday_{YF_INTERVAL_MAP[interval]}"


def default_universe() -> list[str]:
    """SP500 ∪ RUSSELL1000 — same default as jobs.market_us.list_active_tickers(None)."""
    return sorted(
        set(get_index_tickers("SP500")) | set(get_index_tickers("RUSSELL1000"))
    )


def save_rows(conn, df: pd.DataFrame) -> int:
    """INSERT IGNORE 写 prices_intraday，PRIMARY KEY 自动去重。"""
    sql = """
        INSERT IGNORE INTO prices_intraday
          (ticker, `interval`, datetime, open, high, low, close, volume)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """
    rows = [
        (
            r.ticker,
            r.interval,
            r.datetime,
            to_float(getattr(r, "open", None)),
            to_float(getattr(r, "high", None)),
            to_float(getattr(r, "low", None)),
            to_float(r.close),
            to_int(getattr(r, "volume", None)),
        )
        for r in df.itertuples(index=False)
    ]
    with conn.cursor() as cur:
        cur.executemany(sql, rows)
    conn.commit()
    return len(rows)


def _download_single(
    ticker: str,
    yf_symbol: str,
    start_date: date,
    end_date: date,
    yf_interval: str,
) -> Optional[pd.DataFrame]:
    """单独下载单个 ticker（批量响应缺席时的 fallback）。"""
    try:
        df = download_with_retry(
            tickers=yf_symbol,
            start=start_date.strftime("%Y-%m-%d"),
            end=end_date.strftime("%Y-%m-%d"),
            interval=yf_interval,
            group_by="ticker",
            threads=False,
            timeout=YF_TIMEOUT,
            context=f"[{ticker} single] ",
        )
        if df is None or df.empty:
            return None
        return df
    except Exception as e:
        log.warning(f"[{ticker}] 单独下载失败: {e}")
        return None


def _download_and_save(
    conn,
    tickers: List[str],
    *,
    spec: IntradaySpec,
    start_date: date,
    last_trading: date,
    result: Dict[str, str],
) -> None:
    end_date = last_trading + timedelta(days=1)
    yf_symbols = [to_yfinance_us(t) for t in tickers]

    log.info(
        f"[{spec.label}] 下载 {len(tickers)} 只，{start_date} ~ {last_trading}"
    )

    try:
        df = download_with_retry(
            tickers=yf_symbols,
            start=start_date.strftime("%Y-%m-%d"),
            end=end_date.strftime("%Y-%m-%d"),
            interval=spec.yf_interval,
            threads=False,
            timeout=YF_TIMEOUT,
            retry_count=YF_RETRY_COUNT,
            context=f"[{spec.label}] ",
        )
    except Exception as last_exc:
        msg = f"yfinance failed after {YF_RETRY_COUNT} retries: {last_exc}"
        log.error(msg)
        for t in tickers:
            set_sync_error(conn, t, spec.data_type, msg)
            result[t] = f"error: {last_exc}"
        return

    is_multi = (
        df is not None
        and not df.empty
        and isinstance(df.columns, pd.MultiIndex)
    )
    top_level = set(df.columns.get_level_values(0)) if is_multi else set()

    for t in tickers:
        yf_t = to_yfinance_us(t)
        if is_multi:
            if yf_t not in top_level:
                log.warning(f"[{t}] not in batch response, retrying solo...")
                solo_df = _download_single(
                    t, yf_t, start_date, end_date, spec.yf_interval
                )
                if solo_df is not None and not solo_df.empty:
                    normalized = normalize_intraday_frame(
                        t, spec.interval, solo_df
                    )
                    if not normalized.empty:
                        try:
                            rows_inserted = save_rows(conn, normalized)
                            new_last = normalized["datetime"].max().date()
                            set_sync_ok(
                                conn, t, spec.data_type, new_last, rows_inserted
                            )
                            result[t] = "ok"
                            log.info(
                                f"[{t}] 单独拉取成功：写入 {rows_inserted} 条"
                            )
                            continue
                        except Exception as e:
                            log.error(f"[{t}] 单独拉取写库失败: {e}")
                set_sync_error(
                    conn, t, spec.data_type, "yfinance: ticker not in response"
                )
                result[t] = "no_data"
                continue
            sub = df[yf_t]
        elif df is not None and not df.empty and len(tickers) == 1:
            sub = df
        else:
            log.warning(f"[{t}] no data in response")
            set_sync_error(
                conn, t, spec.data_type, "yfinance: empty or unexpected response"
            )
            result[t] = "no_data"
            continue

        normalized = normalize_intraday_frame(t, spec.interval, sub)
        if normalized.empty:
            log.warning(f"[{t}] empty frame")
            set_sync_error(conn, t, spec.data_type, "yfinance: empty frame")
            result[t] = "no_data"
            continue
        try:
            rows_inserted = save_rows(conn, normalized)
            new_last = normalized["datetime"].max().date()
            set_sync_ok(conn, t, spec.data_type, new_last, rows_inserted)
            result[t] = "ok"
            log.info(f"[{t}] 写入 {rows_inserted} 条，最新={new_last}")
        except Exception as e:
            log.error(f"[{t}] 写库失败: {e}")
            if isinstance(e, (pymysql.err.OperationalError, pymysql.err.InterfaceError)):
                log.error("DB 连接断开，停止处理剩余 ticker")
                result[t] = f"error: {e}"
                raise
            try:
                set_sync_error(conn, t, spec.data_type, str(e))
            except Exception as db_err:
                log.error(f"无法写入 sync_error（DB 可能已断开）: {db_err}")
            result[t] = f"error: {e}"


def run_intraday_batch(
    tickers: Optional[List[str]],
    *,
    spec: IntradaySpec,
    full_rebase: bool = False,
) -> Dict[str, str]:
    """Probe → pending → batch download → normalize → write → sync.

    tickers=None resolves default universe only after a successful probe
    (avoids index lookups when API is rate-limited / empty).
    """
    latest_date, status = probe_intraday(spec.interval)

    if status == "no_data":
        log.warning(
            f"[{spec.label}] AAPL 无数据（周末/假期或未更新），跳过本次更新"
        )
        return {}
    if status == "rate_limit":
        log.warning(f"[{spec.label}] yfinance 被限速，跳过本次更新")
        return {}
    if status == "error":
        log.error(f"[{spec.label}] AAPL 测试失败，跳过本次更新")
        return {}

    # Yahoo lookback window is relative to today; floor must stay inside it.
    floor_date = date.today() - timedelta(days=spec.lookback_days - 1)
    last_trading = latest_date

    log.info(f"[{spec.label}] AAPL 验证通过，范围：{floor_date} ~ {last_trading}")

    if tickers is None:
        tickers = default_universe()
    if not tickers:
        return {}

    result: Dict[str, str] = {}
    conn = get_conn()
    try:
        pending: list[tuple[str, date]] = []
        if full_rebase:
            pending = [(t, floor_date) for t in tickers]
        else:
            last_map = get_last_sync_map(conn, tickers, spec.data_type)
            for t in tickers:
                last = last_map.get(t)
                if last is None:
                    pending.append((t, floor_date))
                elif last >= last_trading:
                    result[t] = "ok"
                else:
                    start = max(last + timedelta(days=1), floor_date)
                    pending.append((t, start))

        if not pending:
            log.info(f"[{spec.label}] 所有 ticker 已是最新，无需更新")
            return result

        log.info(f"[{spec.label}] 需更新 {len(pending)} 只 ticker")
        pending.sort(key=lambda x: x[1])

        pair_batches = list(chunked(pending, YF_BATCH_SIZE))
        for idx, batch_pairs in enumerate(pair_batches, 1):
            batch = [t for t, _ in batch_pairs]
            batch_start = min(s for _, s in batch_pairs)
            _download_and_save(
                conn,
                batch,
                spec=spec,
                start_date=batch_start,
                last_trading=last_trading,
                result=result,
            )
            if idx < len(pair_batches):
                sleep_between_batches(spec.label)

        return result
    finally:
        conn.close()
