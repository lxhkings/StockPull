"""
intraday_updater_us.py — 美股分钟级行情拉取（15m / 1h）

数据源: yfinance 免费 tier
存储: prices_intraday 表
Sync: sync_log data_type='intraday_15m'|'intraday_60m'
"""

from __future__ import annotations

import logging
import random
import signal
import time
from datetime import date, timedelta
from typing import Optional

import pandas as pd
import pymysql.err
import yfinance as yf

from config import (
    YF_BATCH_DELAY_BASE,
    YF_BATCH_DELAY_JITTER,
    YF_BATCH_SIZE,
    YF_RETRY_COUNT,
    YF_TIMEOUT,
)
from data.base import to_float, to_int
from data.stock_updater_us import _last_us_trading_date
from db import get_conn, get_last_sync, set_sync_error, set_sync_ok

log = logging.getLogger(__name__)

# interval → yfinance 参数字符串
YF_INTERVAL_MAP: dict[str, str] = {
    "15m": "15m",
    "1h":  "60m",
}

# interval → yfinance 免费 tier 最大可拉天数
INTERVAL_LOOKBACK_DAYS: dict[str, int] = {
    "15m": 60,
    "1h":  730,
}

SUPPORTED_INTERVALS = list(YF_INTERVAL_MAP.keys())


def _sync_type(interval: str) -> str:
    """'15m' → 'intraday_15m', '1h' → 'intraday_60m'"""
    return f"intraday_{YF_INTERVAL_MAP[interval]}"


def _download_single(ticker: str, yf_symbol: str, start_date: date, end_date: date, interval: str) -> Optional[pd.DataFrame]:
    """单独下载单个 ticker 的数据（批量失败时的 fallback）。"""
    try:
        df = yf.download(
            tickers=yf_symbol,
            start=start_date.strftime("%Y-%m-%d"),
            end=end_date.strftime("%Y-%m-%d"),
            interval=interval,
            group_by="ticker",
            auto_adjust=False,
            actions=False,
            threads=False,
            progress=False,
            timeout=YF_TIMEOUT,
        )
        if df is None or df.empty:
            return None
        # 单 ticker 返回 plain DataFrame（无 MultiIndex）
        return df
    except Exception as e:
        log.warning(f"[{ticker}] 单独下载失败: {e}")
        return None


def _test_aapl_intraday(interval: str) -> tuple[Optional[date], str]:
    """
    测试 AAPL 是否有最近交易日数据，判断 yfinance intraday API 是否可用

    Returns:
        (latest_date, status) 其中 status 为:
        - "ok": 有数据，返回最新日期
        - "no_data": 无数据（周末/假期或未更新）
        - "error": 其他错误
    """
    try:
        # 计算 Yahoo 730 天限制的有效范围
        today = date.today()
        floor = today - timedelta(days=INTERVAL_LOOKBACK_DAYS[interval] - 1)
        end = today + timedelta(days=1)

        df = yf.download(
            tickers="AAPL",
            start=floor.strftime("%Y-%m-%d"),
            end=end.strftime("%Y-%m-%d"),
            interval=YF_INTERVAL_MAP[interval],
            group_by="ticker",
            auto_adjust=False,
            actions=False,
            threads=False,
            progress=False,
            timeout=YF_TIMEOUT,
        )

        if df is None or df.empty:
            return None, "no_data"

        latest = df.index[-1].date()
        log.info(f"[AAPL {interval}] 测试成功：最新日期 {latest}，范围 {floor} ~ {latest}")
        return latest, "ok"

    except Exception as e:
        log.error(f"[AAPL {interval}] 测试失败: {e}")
        return None, "error"


def _yf_symbol(ticker: str) -> str:
    """DB ticker → yfinance symbol: BRK.B → BRK-B"""
    return ticker.upper().replace(".", "-")


def _normalize_frame(ticker: str, interval: str, sub: pd.DataFrame) -> pd.DataFrame:
    """yfinance 单 ticker 子表 → 标准列 [ticker, interval, datetime, open, high, low, close, volume]"""
    cols = ["ticker", "interval", "datetime", "open", "high", "low", "close", "volume"]
    if sub is None or sub.empty:
        return pd.DataFrame(columns=cols)

    df = sub.reset_index()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df.columns = [str(c).lower() for c in df.columns]

    for cand in ("datetime", "date", "index"):
        if cand in df.columns:
            df = df.rename(columns={cand: "datetime"})
            break

    df["datetime"] = pd.to_datetime(df["datetime"])
    # 剥除时区，MySQL DATETIME 无时区（yfinance 返回 UTC）
    if df["datetime"].dt.tz is not None:
        df["datetime"] = df["datetime"].dt.tz_convert("UTC").dt.tz_localize(None)

    df["ticker"] = ticker
    df["interval"] = interval
    df = df.dropna(subset=["datetime", "close"])
    return df[cols].sort_values("datetime").reset_index(drop=True)


def _save_rows(conn, df: pd.DataFrame) -> int:
    """INSERT IGNORE 写 prices_intraday，PRIMARY KEY 自动去重"""
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


def update_intraday(interval: str, full_rebase: bool = False) -> dict[str, str]:
    """批量增量拉取美股 intraday，写入 prices_intraday。

    Args:
        interval: '15m' 或 '1h'
        full_rebase: True 时忽略 sync_log，从 floor_date 全量拉取
    Returns:
        {ticker: 'ok' | 'no_data' | 'error: <msg>'}
    """
    if interval not in SUPPORTED_INTERVALS:
        raise ValueError(f"Unsupported interval: {interval}. Supported: {SUPPORTED_INTERVALS}")

    # 先用 AAPL 测试 API 是否可用，并获取实际最新日期
    latest_date, status = _test_aapl_intraday(interval)

    if status == "no_data":
        log.warning(f"[intraday {interval}] AAPL 无数据（周末/假期或未更新），跳过本次更新")
        return {}
    elif status == "error":
        log.error(f"[intraday {interval}] AAPL 测试失败，跳过本次更新")
        return {}

    # 用 AAPL 的实际最新日期计算 floor_date（而非理论推算）
    lookback_days = INTERVAL_LOOKBACK_DAYS[interval]
    floor_date = latest_date - timedelta(days=lookback_days - 1)
    last_trading = latest_date

    log.info(f"[intraday {interval}] AAPL 验证通过，范围：{floor_date} ~ {last_trading}")

    from data.market_us import list_active_tickers
    tickers = list_active_tickers()

    result: dict[str, str] = {}
    conn = get_conn()
    try:
        sync_type = _sync_type(interval)

        pending: list[tuple[str, date]] = []
        for t in tickers:
            if full_rebase:
                pending.append((t, floor_date))
            else:
                last = get_last_sync(conn, t, sync_type)
                if last is None:
                    pending.append((t, floor_date))
                elif last >= last_trading:
                    result[t] = "ok"
                else:
                    start = max(last + timedelta(days=1), floor_date)
                    pending.append((t, start))

        if not pending:
            log.info(f"[intraday {interval}] 所有 ticker 已是最新，无需更新")
            return result

        log.info(f"[intraday {interval}] 需更新 {len(pending)} 只 ticker")

        pending.sort(key=lambda x: x[1])

        for i in range(0, len(pending), YF_BATCH_SIZE):
            batch_pairs = pending[i:i + YF_BATCH_SIZE]
            batch = [t for t, _ in batch_pairs]
            batch_start = min(s for _, s in batch_pairs)
            _download_and_save(conn, batch, interval, batch_start, last_trading, result)
            if i + YF_BATCH_SIZE < len(pending):
                delay = YF_BATCH_DELAY_BASE + random.uniform(
                    -YF_BATCH_DELAY_JITTER, YF_BATCH_DELAY_JITTER
                )
                log.debug(f"[intraday {interval}] 等待 {delay:.1f}s")
                time.sleep(delay)

        return result
    finally:
        conn.close()


def _download_and_save(
    conn,
    tickers: list[str],
    interval: str,
    start_date: date,
    last_trading: date,
    result: dict[str, str],
) -> None:
    """下载一批 ticker 的 intraday 数据并保存到 prices_intraday。"""
    end_date = last_trading + timedelta(days=1)
    yf_interval = YF_INTERVAL_MAP[interval]
    yf_symbols = [_yf_symbol(t) for t in tickers]
    sync_type = _sync_type(interval)

    log.info(f"[intraday {interval}] 下载 {len(tickers)} 只，{start_date} ~ {last_trading}")

    df = None
    last_exc: Optional[Exception] = None
    for attempt in range(YF_RETRY_COUNT):
        try:
            signal.signal(signal.SIGINT, signal.SIG_DFL)
            df = yf.download(
                tickers=yf_symbols,
                start=start_date.strftime("%Y-%m-%d"),
                end=end_date.strftime("%Y-%m-%d"),
                interval=yf_interval,
                group_by="ticker",
                auto_adjust=False,
                actions=False,
                threads=False,
                progress=False,
                timeout=YF_TIMEOUT,
            )
            last_exc = None
            break
        except Exception as e:
            last_exc = e
            if attempt < YF_RETRY_COUNT - 1:
                backoff = 5 * (3 ** attempt)
                log.warning(f"yf.download attempt {attempt + 1} failed, retry in {backoff}s: {e}")
                time.sleep(backoff)

    if last_exc is not None:
        msg = f"yfinance failed after {YF_RETRY_COUNT} retries: {last_exc}"
        log.error(msg)
        for t in tickers:
            set_sync_error(conn, t, sync_type, msg)
            result[t] = f"error: {last_exc}"
        return

    # yfinance: 2+ tickers → MultiIndex DataFrame; single ticker → plain DataFrame
    is_multi = df is not None and not df.empty and isinstance(df.columns, pd.MultiIndex)
    top_level = set(df.columns.get_level_values(0)) if is_multi else set()

    for t in tickers:
        yf_t = _yf_symbol(t)
        if is_multi:
            if yf_t not in top_level:
                log.warning(f"[{t}] not in batch response, retrying solo...")
                # 尝试单独下载该 ticker
                solo_df = _download_single(t, yf_t, start_date, end_date, yf_interval)
                if solo_df is not None and not solo_df.empty:
                    normalized = _normalize_frame(t, interval, solo_df)
                    if not normalized.empty:
                        try:
                            rows_inserted = _save_rows(conn, normalized)
                            new_last = normalized["datetime"].max().date()
                            set_sync_ok(conn, t, sync_type, new_last, rows_inserted)
                            result[t] = "ok"
                            log.info(f"[{t}] 单独拉取成功：写入 {rows_inserted} 条")
                            continue
                        except Exception as e:
                            log.error(f"[{t}] 单独拉取写库失败: {e}")
                # 单独拉取也失败
                set_sync_error(conn, t, sync_type, "yfinance: ticker not in response")
                result[t] = "no_data"
                continue
            sub = df[yf_t]
        elif df is not None and not df.empty and len(tickers) == 1:
            sub = df  # single-ticker plain DataFrame
        else:
            log.warning(f"[{t}] no data in response")
            set_sync_error(conn, t, sync_type, "yfinance: empty or unexpected response")
            result[t] = "no_data"
            continue

        normalized = _normalize_frame(t, interval, sub)
        if normalized.empty:
            log.warning(f"[{t}] empty frame")
            set_sync_error(conn, t, sync_type, "yfinance: empty frame")
            result[t] = "no_data"
            continue
        try:
            rows_inserted = _save_rows(conn, normalized)
            new_last = normalized["datetime"].max().date()
            set_sync_ok(conn, t, sync_type, new_last, rows_inserted)
            result[t] = "ok"
            log.info(f"[{t}] 写入 {rows_inserted} 条，最新={new_last}")
        except Exception as e:
            log.error(f"[{t}] 写库失败: {e}")
            # 检查是否是连接错误（应该立即停止，不应继续尝试写入）
            if isinstance(e, (pymysql.err.OperationalError, pymysql.err.InterfaceError)):
                log.error(f"DB 连接断开，停止处理剩余 ticker")
                result[t] = f"error: {e}"
                raise  # 连接错误应该向上抛出，停止整个批次
            # 非连接错误：尝试记录到 sync_log（可能成功）
            try:
                set_sync_error(conn, t, sync_type, str(e))
            except Exception as db_err:
                log.error(f"无法写入 sync_error（DB 可能已断开）: {db_err}")
            result[t] = f"error: {e}"
