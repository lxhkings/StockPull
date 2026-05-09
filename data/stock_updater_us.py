"""
stock_updater.py — 股票行情更新

数据源：yfinance（增量，按日期续拉）

职责：
- 从 yfinance 拉取股票历史行情数据
- 支持单只入口和批量入口（pipeline 用批量）
- INSERT IGNORE 通过 prices.UNIQUE KEY (ticker, date) 自动防重
"""

import time
import logging
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
from typing import Optional, List, Dict

from config import (
    HISTORY_YEARS_US as HISTORY_YEARS,
    YF_BATCH_SIZE, YF_RETRY_COUNT, YF_TIMEOUT,
    YF_LOOKBACK_DAYS, YF_THREADS,
)
from db import get_conn, get_last_sync, set_sync_ok, set_sync_error
from data.base import to_float, to_int

log = logging.getLogger(__name__)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 单只入口（向后兼容）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def update_prices(ticker: str, _legacy: Optional[str] = None) -> None:
    """
    单只 ticker 增量更新（薄包装，内部调 update_prices_batch）

    Args:
        ticker: 股票代码（如 AAPL）
        _legacy: 已弃用，原 stooq_ticker 参数，传任何值都被忽略
    """
    update_prices_batch([ticker])


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 批量入口（pipeline 用）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def update_prices_batch(tickers: List[str]) -> Dict[str, str]:
    """
    批量增量拉取一组 ticker 的行情，写入 prices 表

    Args:
        tickers: DB 形式 ticker 列表

    Returns:
        {ticker: "ok" | "no_data" | "error: <msg>"}
    """
    if not tickers:
        return {}

    conn = get_conn()
    try:
        per_ticker_start = {}
        for t in tickers:
            last = get_last_sync(conn, t, "price")
            if last is None:
                start_dt = (datetime.today() - timedelta(days=365 * HISTORY_YEARS)).date()
            else:
                start_dt = last - timedelta(days=YF_LOOKBACK_DAYS)
            per_ticker_start[t] = start_dt

        batch_start = min(per_ticker_start.values())
        end_dt = (datetime.today() + timedelta(days=1)).date()
        yf_symbols = [_yf_symbol(t) for t in tickers]

        df = None
        last_exc = None
        for attempt in range(YF_RETRY_COUNT):
            try:
                df = yf.download(
                    tickers=yf_symbols,
                    start=batch_start.strftime("%Y-%m-%d"),
                    end=end_dt.strftime("%Y-%m-%d"),
                    interval="1d",
                    group_by="ticker",
                    auto_adjust=False,
                    actions=False,
                    threads=YF_THREADS,
                    progress=False,
                    timeout=YF_TIMEOUT,
                    repair=False,
                )
                last_exc = None
                break
            except Exception as e:
                last_exc = e
                if attempt < YF_RETRY_COUNT - 1:
                    backoff = 5 * (3 ** attempt)
                    log.warning(f"yf.download 第 {attempt+1} 次失败，{backoff}s 后重试: {e}")
                    time.sleep(backoff)

        if last_exc is not None:
            msg = f"yfinance batch failed after {YF_RETRY_COUNT} retries: {last_exc}"
            log.error(msg)
            result = {}
            for t in tickers:
                set_sync_error(conn, t, "price", msg)
                result[t] = f"error: {last_exc}"
            return result

        result = {}
        top_level = set()
        if df is not None and not df.empty and isinstance(df.columns, pd.MultiIndex):
            top_level = set(df.columns.get_level_values(0))

        for t in tickers:
            yf_t = _yf_symbol(t)
            if yf_t not in top_level:
                set_sync_error(conn, t, "price", "yfinance: ticker not in response")
                result[t] = "no_data"
                continue
            sub = df[yf_t]
            normalized = _normalize_yf_frame(t, sub)
            if normalized.empty:
                set_sync_error(conn, t, "price", "yfinance: empty frame")
                result[t] = "no_data"
                continue
            try:
                rows_inserted = _save_prices(conn, t, normalized)
                new_last = normalized["date"].max()
                set_sync_ok(conn, t, "price", new_last, rows_inserted)
                result[t] = "ok"
                log.info(f"[{t}] 写入 {rows_inserted} 条，最新={new_last}")
            except Exception as e:
                log.error(f"[{t}] 写库失败: {e}")
                set_sync_error(conn, t, "price", str(e))
                result[t] = f"error: {e}"

        return result
    finally:
        conn.close()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 内部工具
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _yf_symbol(ticker: str) -> str:
    """DB ticker → yfinance ticker（BRK.B → BRK-B）"""
    return ticker.upper().replace(".", "-")


def _normalize_yf_frame(ticker: str, sub: pd.DataFrame) -> pd.DataFrame:
    """yfinance 单 ticker 子表 → [ticker, date, open, high, low, close, volume]"""
    cols = ["ticker", "date", "open", "high", "low", "close", "volume"]
    if sub is None or sub.empty:
        return pd.DataFrame(columns=cols)

    df = sub.reset_index()
    df.columns = [str(c).lower() for c in df.columns]
    if "date" not in df.columns:
        for cand in ("datetime", "index"):
            if cand in df.columns:
                df = df.rename(columns={cand: "date"})
                break

    df["date"] = pd.to_datetime(df["date"]).dt.date
    df["ticker"] = ticker
    df = df.dropna(subset=["date", "close"])
    df = df[cols].sort_values("date").reset_index(drop=True)
    return df


def _save_prices(conn, ticker: str, df: pd.DataFrame) -> int:
    """INSERT IGNORE 写 prices 表，UNIQUE KEY (ticker, date) 自动去重"""
    sql = """
        INSERT IGNORE INTO prices (ticker, date, open, high, low, close, volume)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """
    rows = [
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
    with conn.cursor() as cur:
        cur.executemany(sql, rows)
    conn.commit()
    return len(rows)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Ticker 映射工具
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def guess_yf_ticker(ticker: str) -> str:
    """
    根据 DB ticker 推测 yfinance 调用代码
    Args:
        ticker: 如 AAPL、BRK.B
    Returns:
        如 AAPL、BRK-B
    """
    return _yf_symbol(ticker)


# 过渡期别名：旧调用方仍可 import guess_stooq_ticker
guess_stooq_ticker = guess_yf_ticker