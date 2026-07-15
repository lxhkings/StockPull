"""
stock_updater.py — 股票行情更新

数据源：yfinance（增量，按日期续拉）

职责：
- 从 yfinance 拉取股票历史行情数据
- 支持单只入口和批量入口（pipeline 用批量）
- INSERT IGNORE 通过 prices.UNIQUE KEY (ticker, date) 自动防重
"""

import time
import random
import logging
import pandas as pd
from datetime import timedelta, date
from typing import Optional, List, Dict

from core.batch_utils import chunked

from config import (
    HISTORY_YEARS_US as HISTORY_YEARS,
    START_DATE_US,
    YF_BATCH_SIZE, YF_RETRY_COUNT, YF_TIMEOUT,
    YF_LOOKBACK_DAYS, YF_THREADS,
    YF_BATCH_DELAY_BASE, YF_BATCH_DELAY_JITTER,
)
from core.db_client import get_conn
from modules.sync_log import get_last_sync_map, set_sync_error
from modules.price_write import flush_prices_and_sync
from core.http_utils import to_float, to_int
from core.trading_calendar import last_us_trading_date
from apis.yfinance.client import download_with_retry
from apis.yfinance.ticker_utils import to_yfinance_us

log = logging.getLogger(__name__)


def _test_aapl_data(target_date: date) -> tuple[Optional[pd.DataFrame], str]:
    """
    测试 AAPL 是否有目标日期数据，判断 yfinance 是否已更新

    Returns:
        (DataFrame, status) 其中 status 为:
        - "ok": 有目标日期数据
        - "rate_limit": 被限速
        - "error": 其他错误
        - "no_data": 空/无目标日
    """
    end_dt = target_date + timedelta(days=1)
    start_dt = target_date - timedelta(days=5)

    try:
        df = download_with_retry(
            tickers="AAPL",
            start=start_dt.strftime("%Y-%m-%d"),
            end=end_dt.strftime("%Y-%m-%d"),
            interval="1d",
            group_by="column",
            threads=False,
            timeout=30,
            context="[AAPL probe] ",
        )
        if df is None or df.empty:
            return None, "no_data"

        df = df.reset_index()
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df.columns = [str(c).lower() for c in df.columns]

        if "date" not in df.columns and "datetime" in df.columns:
            df = df.rename(columns={"datetime": "date"})
        if "date" not in df.columns and "index" in df.columns:
            df = df.rename(columns={"index": "date"})

        df["date"] = pd.to_datetime(df["date"]).dt.date
        if target_date in df["date"].values:
            return df, "ok"
        return None, "no_data"
    except Exception as e:
        err_msg = str(e)
        if "RateLimit" in err_msg or "Too Many Requests" in err_msg:
            log.warning(f"[AAPL] yfinance 被限速: {e}")
            return None, "rate_limit"
        log.warning(f"[AAPL] 测试请求失败: {e}")
        return None, "error"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 批量入口（pipeline 用）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def update_prices_batch(tickers: List[str], full_rebase: bool = False, years: Optional[int] = None) -> Dict[str, str]:
    """
    批量增量拉取一组 ticker 的行情，写入 prices 表

    Args:
        tickers: DB 形式 ticker 列表
        full_rebase: True 时强制从历史起点拉取（忽略 sync_log）
        years: 指定历史年数（None 时使用 config 默认值）

    Returns:
        {ticker: "ok" | "no_data" | "error: <msg>"}
    """
    if not tickers:
        return {}

    # 先用 AAPL 测试 yfinance 是否已更新最近数据
    last_trading = last_us_trading_date()
    test_df, status = _test_aapl_data(last_trading)

    if status == "rate_limit":
        log.warning("[AAPL] yfinance 被限速，跳过本次增量更新，稍后重试")
        return {t: "error: rate_limit" for t in tickers}
    elif status == "no_data":
        log.warning(f"[AAPL] yfinance 暂无 {last_trading} 数据（市场未开或未更新），跳过本次增量更新")
        return {t: "error: no_data" for t in tickers}
    elif status == "error":
        log.warning("[AAPL] 测试请求失败，跳过本次增量更新")
        return {t: "error: test_failed" for t in tickers}

    log.info(f"[AAPL] yfinance 已有 {last_trading} 数据，开始批量下载")

    result = {}
    conn = get_conn()
    try:
        if full_rebase:
            # full_rebase: 所有 ticker 从历史起点开始拉取
            actual_years = years if years else HISTORY_YEARS
            log.info(f"[batch] rebase: {len(tickers)} ticker 拉取 {actual_years} 年历史")
            batches = list(chunked(tickers, YF_BATCH_SIZE))
            for idx, batch in enumerate(batches, 1):
                _download_and_save(conn, batch, None, result, years=actual_years)
                if idx < len(batches):
                    delay = YF_BATCH_DELAY_BASE + random.uniform(-YF_BATCH_DELAY_JITTER, YF_BATCH_DELAY_JITTER)
                    log.debug(f"[batch] 等待 {delay:.1f}s 后继续")
                    time.sleep(delay)
        else:
            # 增量模式：区分新 ticker 和已同步 ticker
            new_tickers = []
            pending_tickers = []  # 需要增量更新的 ticker
            pending_start = None

            # 增量窗口上限：不超过 YF_LOOKBACK_DAYS 天前
            lookback_floor = last_trading - timedelta(days=YF_LOOKBACK_DAYS)

            last_map = get_last_sync_map(conn, tickers, "price")
            for t in tickers:
                last = last_map.get(t)
                if last is None:
                    new_tickers.append(t)
                elif last < last_trading:
                    # 只有未同步到最新交易日的 ticker 才需要更新
                    start_dt = max(last + timedelta(days=1), lookback_floor)
                    pending_tickers.append(t)
                    if pending_start is None or start_dt < pending_start:
                        pending_start = start_dt
                # 已同步到 last_trading 的 ticker 跳过

            # 新 ticker 回填历史
            if new_tickers:
                log.info(f"[batch] {len(new_tickers)} 新 ticker 需回填 {HISTORY_YEARS} 年历史")
                batches_new = list(chunked(new_tickers, YF_BATCH_SIZE))
                for idx, batch_new in enumerate(batches_new, 1):
                    _download_and_save(conn, batch_new, None, result)
                    if idx < len(batches_new):
                        delay = YF_BATCH_DELAY_BASE + random.uniform(-YF_BATCH_DELAY_JITTER, YF_BATCH_DELAY_JITTER)
                        log.debug(f"[batch] 等待 {delay:.1f}s 后继续")
                        time.sleep(delay)

            # 待更新 ticker 增量同步
            if pending_tickers:
                log.info(f"[batch] {len(pending_tickers)} ticker 需增量更新（从 {pending_start} 到 {last_trading}，窗口上限 {YF_LOOKBACK_DAYS} 天）")
                batches_pending = list(chunked(pending_tickers, YF_BATCH_SIZE))
                for idx, batch_pending in enumerate(batches_pending, 1):
                    _download_and_save(conn, batch_pending, pending_start, result)
                    if idx < len(batches_pending):
                        delay = YF_BATCH_DELAY_BASE + random.uniform(-YF_BATCH_DELAY_JITTER, YF_BATCH_DELAY_JITTER)
                        log.debug(f"[batch] 等待 {delay:.1f}s 后继续")
                        time.sleep(delay)
            else:
                log.info(f"[batch] 所有 ticker 已同步到 {last_trading}，无需增量更新")

        return result
    finally:
        conn.close()


def _download_and_save(conn, tickers: List[str], start_date: Optional[date], result: Dict[str, str], years: Optional[int] = None) -> None:
    """下载一批 ticker 数据并保存到数据库"""
    if not tickers:
        return

    # start_date 为 None 表示新 ticker，从历史起点到最近收盘日
    if start_date is None:
        last_trading = last_us_trading_date()
        if years:
            # 指定年数，从 last_trading 往回推算
            start_date = last_trading - timedelta(days=365 * years)
        else:
            # 默认从 START_DATE_US 开始（2010-01-01）
            start_date = date.fromisoformat(START_DATE_US)

    # end_dt 设为最近收盘日 + 1 天（yfinance end 参数不包含该日期）
    last_trading = last_us_trading_date()
    end_dt = last_trading + timedelta(days=1)
    yf_symbols = [to_yfinance_us(t) for t in tickers]

    log.info(f"[batch] 下载 {len(tickers)} 只股票, 日期范围: {start_date} ~ {last_trading}")

    try:
        df = download_with_retry(
            tickers=yf_symbols,
            start=start_date.strftime("%Y-%m-%d"),
            end=end_dt.strftime("%Y-%m-%d"),
            interval="1d",
            threads=YF_THREADS,
            timeout=YF_TIMEOUT,
            retry_count=YF_RETRY_COUNT,
            repair=False,
            context="[batch] ",
        )
    except Exception as last_exc:
        msg = f"yfinance batch failed after {YF_RETRY_COUNT} retries: {last_exc}"
        log.error(msg)
        for t in tickers:
            set_sync_error(conn, t, "price", msg)
            result[t] = f"error: {last_exc}"
        return

    top_level = set()
    if df is not None and not df.empty and isinstance(df.columns, pd.MultiIndex):
        top_level = set(df.columns.get_level_values(0))

    price_rows: list = []
    sync_rows: list = []
    ok_tickers: list = []

    for t in tickers:
        yf_t = to_yfinance_us(t)
        if yf_t not in top_level:
            log.warning(f"[{t}] yfinance: ticker not in response, 无数据")
            set_sync_error(conn, t, "price", "yfinance: ticker not in response")
            result[t] = "no_data"
            continue
        sub = df[yf_t]
        normalized = _normalize_yf_frame(t, sub)
        if normalized.empty:
            log.warning(f"[{t}] yfinance: empty frame, 无数据")
            set_sync_error(conn, t, "price", "yfinance: empty frame")
            result[t] = "no_data"
            continue
        rows = _price_rows_from_df(normalized)
        new_last = normalized["date"].max()
        price_rows.extend(rows)
        sync_rows.append((t, "price", new_last, len(rows), "ok", ""))
        ok_tickers.append(t)
        result[t] = "ok"
        log.info(f"[{t}] 写入 {len(rows)} 条，最新={new_last}")

    if price_rows or sync_rows:
        try:
            flush_prices_and_sync(conn, price_rows, sync_rows, on_duplicate=False)
        except Exception as e:
            log.error(f"[batch] 写库失败: {e}")
            for t in ok_tickers:
                set_sync_error(conn, t, "price", str(e))
                result[t] = f"error: {e}"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 内部工具
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _normalize_yf_frame(ticker: str, sub: pd.DataFrame) -> pd.DataFrame:
    """yfinance 单 ticker 子表 → [ticker, date, open, high, low, close, volume]"""
    cols = ["ticker", "date", "open", "high", "low", "close", "volume"]
    if sub is None or sub.empty:
        return pd.DataFrame(columns=cols)

    df = sub.reset_index()
    # 处理 MultiIndex 列名（yfinance 单 ticker 也返回 MultiIndex）
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
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


def _price_rows_from_df(df: pd.DataFrame) -> list:
    """DataFrame → price row tuples for flush_prices_and_sync."""
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
