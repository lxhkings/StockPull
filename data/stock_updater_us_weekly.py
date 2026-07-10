# data/stock_updater_us_weekly.py
"""
stock_updater_us_weekly.py — 美股周线行情更新

数据源：yfinance (interval="1wk")
写入：prices_weekly 表
sync_log data_type: "price_weekly"

逻辑完全镜像 stock_updater_us.py，差异仅在 interval、表名、data_type。
"""

import time
import signal
import random
import logging
from datetime import datetime, timedelta, date
from typing import Optional, List, Dict

from core.batch_utils import chunked

import pandas as pd
import yfinance as yf

from config import (
    START_DATE_US,
    YF_BATCH_SIZE, YF_RETRY_COUNT, YF_TIMEOUT,
    YF_LOOKBACK_DAYS, YF_THREADS,
    YF_BATCH_DELAY_BASE, YF_BATCH_DELAY_JITTER,
)
from db import get_conn, get_last_sync, set_sync_ok, set_sync_error
from data.base import to_float, to_int
from data.yf_client import download_with_retry

log = logging.getLogger(__name__)


def _last_us_weekly_date() -> date:
    """Return Monday of the most recently completed US trading week.

    A week is complete when Friday US close passes (Beijing time: Saturday ~5am).
    yfinance uses Monday as the canonical date for each week.
    """
    now = datetime.now()
    weekday = now.weekday()  # 0=Mon, 5=Sat, 6=Sun
    hour = now.hour
    today = now.date()
    this_monday = today - timedelta(days=weekday)

    # Saturday after 5am Beijing, or Sunday: this week (Mon-Fri) just closed
    if (weekday == 5 and hour >= 5) or weekday == 6:
        return this_monday  # Monday of the week that ended this Friday
    # Mon-Fri, or Saturday before 5am: current week not complete
    return this_monday - timedelta(days=7)  # Monday of the previous week


def _test_aapl_weekly(target_monday: date) -> tuple[Optional[pd.DataFrame], str]:
    """Test if yfinance has weekly data for the week starting target_monday."""
    start = target_monday - timedelta(days=14)
    end = target_monday + timedelta(days=7)
    try:
        signal.signal(signal.SIGINT, signal.SIG_DFL)
        df = yf.download(
            tickers="AAPL",
            start=start.strftime("%Y-%m-%d"),
            end=end.strftime("%Y-%m-%d"),
            interval="1wk",
            progress=False,
            timeout=30,
        )
        if df is None or df.empty:
            return None, "no_data"
        df = df.reset_index()
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df.columns = [str(c).lower() for c in df.columns]
        if "date" not in df.columns and "datetime" in df.columns:
            df = df.rename(columns={"datetime": "date"})
        df["date"] = pd.to_datetime(df["date"]).dt.date
        if target_monday in df["date"].values:
            return df, "ok"
        return None, "no_data"
    except Exception as e:
        err_msg = str(e)
        if "RateLimit" in err_msg or "Too Many Requests" in err_msg:
            log.warning(f"[AAPL weekly] yfinance 被限速: {e}")
            return None, "rate_limit"
        log.warning(f"[AAPL weekly] 测试请求失败: {e}")
        return None, "error"


def update_weekly_batch(tickers: List[str], full_rebase: bool = False) -> Dict[str, str]:
    """批量增量拉取周线，写入 prices_weekly 表。

    Args:
        tickers: DB 格式 ticker 列表
        full_rebase: True 时强制从 START_DATE_US 全量拉取

    Returns:
        {ticker: "ok" | "no_data" | "error: <msg>"}
    """
    if not tickers:
        return {}

    target_monday = _last_us_weekly_date()
    _, status = _test_aapl_weekly(target_monday)

    if status == "rate_limit":
        log.warning("[AAPL weekly] yfinance 被限速，跳过本次周线更新")
        return {t: "error: rate_limit" for t in tickers}
    elif status == "no_data":
        log.warning(f"[AAPL weekly] yfinance 暂无 {target_monday} 周线数据，跳过")
        return {t: "error: no_data" for t in tickers}
    elif status == "error":
        log.warning("[AAPL weekly] 测试请求失败，跳过本次周线更新")
        return {t: "error: test_failed" for t in tickers}

    log.info(f"[AAPL weekly] yfinance 已有 {target_monday} 周线数据，开始批量下载")

    result = {}
    conn = get_conn()
    try:
        if full_rebase:
            log.info(f"[weekly batch] rebase: {len(tickers)} ticker 全量历史")
            batches = list(chunked(tickers, YF_BATCH_SIZE))
            for idx, batch in enumerate(batches, 1):
                _download_and_save_weekly(conn, batch, None, result)
                if idx < len(batches):
                    delay = YF_BATCH_DELAY_BASE + random.uniform(
                        -YF_BATCH_DELAY_JITTER, YF_BATCH_DELAY_JITTER
                    )
                    time.sleep(delay)
        else:
            new_tickers = []
            pending_tickers = []
            pending_start = None
            lookback_floor = target_monday - timedelta(days=YF_LOOKBACK_DAYS)

            for t in tickers:
                last = get_last_sync(conn, t, "price_weekly")
                if last is None:
                    new_tickers.append(t)
                elif last < target_monday:
                    start_dt = max(last + timedelta(days=1), lookback_floor)
                    pending_tickers.append(t)
                    if pending_start is None or start_dt < pending_start:
                        pending_start = start_dt
                # last >= target_monday: already up-to-date, skip

            if new_tickers:
                log.info(f"[weekly batch] {len(new_tickers)} 新 ticker 需回填全量历史")
                batches_new = list(chunked(new_tickers, YF_BATCH_SIZE))
                for idx, batch_new in enumerate(batches_new, 1):
                    _download_and_save_weekly(conn, batch_new, None, result)
                    if idx < len(batches_new):
                        delay = YF_BATCH_DELAY_BASE + random.uniform(
                            -YF_BATCH_DELAY_JITTER, YF_BATCH_DELAY_JITTER
                        )
                        time.sleep(delay)

            if pending_tickers:
                log.info(
                    f"[weekly batch] {len(pending_tickers)} ticker 增量更新"
                    f"（从 {pending_start} 到 {target_monday}）"
                )
                batches_pending = list(chunked(pending_tickers, YF_BATCH_SIZE))
                for idx, batch_pending in enumerate(batches_pending, 1):
                    _download_and_save_weekly(conn, batch_pending, pending_start, result)
                    if idx < len(batches_pending):
                        delay = YF_BATCH_DELAY_BASE + random.uniform(
                            -YF_BATCH_DELAY_JITTER, YF_BATCH_DELAY_JITTER
                        )
                        time.sleep(delay)
            else:
                log.info(f"[weekly batch] 所有 ticker 已同步到 {target_monday}，无需更新")

        return result
    finally:
        conn.close()


def _download_and_save_weekly(
    conn,
    tickers: List[str],
    start_date: Optional[date],
    result: Dict[str, str],
) -> None:
    """下载一批 ticker 周线数据并保存到 prices_weekly。"""
    if not tickers:
        return

    if start_date is None:
        start_date = date.fromisoformat(START_DATE_US)

    target_monday = _last_us_weekly_date()
    end_dt = target_monday + timedelta(days=7)
    yf_symbols = [_yf_symbol(t) for t in tickers]

    log.info(f"[weekly batch] 下载 {len(tickers)} 只股票周线, {start_date} ~ {target_monday}")

    try:
        df = download_with_retry(
            tickers=yf_symbols,
            start=start_date.strftime("%Y-%m-%d"),
            end=end_dt.strftime("%Y-%m-%d"),
            interval="1wk",
            threads=YF_THREADS,
            timeout=YF_TIMEOUT,
            retry_count=YF_RETRY_COUNT,
            repair=False,
            context="[weekly batch] ",
        )
    except Exception as last_exc:
        msg = f"yfinance weekly failed after {YF_RETRY_COUNT} retries: {last_exc}"
        log.error(msg)
        for t in tickers:
            set_sync_error(conn, t, "price_weekly", msg)
            result[t] = f"error: {last_exc}"
        return

    top_level = set()
    if df is not None and not df.empty and isinstance(df.columns, pd.MultiIndex):
        top_level = set(df.columns.get_level_values(0))

    for t in tickers:
        yf_t = _yf_symbol(t)
        if yf_t not in top_level:
            log.warning(f"[{t}] yfinance weekly: ticker not in response")
            set_sync_error(conn, t, "price_weekly", "yfinance: ticker not in response")
            result[t] = "no_data"
            continue
        sub = df[yf_t]
        normalized = _normalize_weekly_frame(t, sub)
        if normalized.empty:
            log.warning(f"[{t}] yfinance weekly: empty frame")
            set_sync_error(conn, t, "price_weekly", "yfinance: empty frame")
            result[t] = "no_data"
            continue
        try:
            rows_inserted = _save_weekly_prices(conn, t, normalized)
            new_last = normalized["date"].max()
            set_sync_ok(conn, t, "price_weekly", new_last, rows_inserted)
            result[t] = "ok"
            log.info(f"[{t}] 周线写入 {rows_inserted} 条，最新={new_last}")
        except Exception as e:
            log.error(f"[{t}] 周线写库失败: {e}")
            set_sync_error(conn, t, "price_weekly", str(e))
            result[t] = f"error: {e}"


def _yf_symbol(ticker: str) -> str:
    """DB ticker → yfinance symbol (BRK.B → BRK-B)."""
    return ticker.upper().replace(".", "-")


def _normalize_weekly_frame(ticker: str, sub: pd.DataFrame) -> pd.DataFrame:
    """yfinance 单 ticker 周线子表 → [ticker, date, open, high, low, close, volume]"""
    cols = ["ticker", "date", "open", "high", "low", "close", "volume"]
    if sub is None or sub.empty:
        return pd.DataFrame(columns=cols)
    df = sub.reset_index()
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


def _save_weekly_prices(conn, ticker: str, df: pd.DataFrame) -> int:
    """INSERT IGNORE 写 prices_weekly 表，UNIQUE KEY (ticker, date) 自动去重。"""
    sql = """
        INSERT IGNORE INTO prices_weekly (ticker, date, open, high, low, close, volume)
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
