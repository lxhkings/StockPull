"""
stock_updater.py — 股票行情更新

数据源：yfinance（增量，按日期续拉）

职责：
- 从 yfinance 拉取股票历史行情数据
- 支持单只入口和批量入口（pipeline 用批量）
- INSERT IGNORE 通过 prices.UNIQUE KEY (ticker, date) 自动防重
"""

import time
import signal
import random
import logging
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta, date
from typing import Optional, List, Dict

from config import (
    HISTORY_YEARS_US as HISTORY_YEARS,
    YF_BATCH_SIZE, YF_RETRY_COUNT, YF_TIMEOUT,
    YF_LOOKBACK_DAYS, YF_THREADS,
    YF_BATCH_DELAY_BASE, YF_BATCH_DELAY_JITTER,
)
from db import get_conn, get_last_sync, set_sync_ok, set_sync_error
from data.base import to_float, to_int

log = logging.getLogger(__name__)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 美股收盘日计算（北京时间视角）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _last_us_trading_date() -> date:
    """
    计算美股最近已收盘的交易日（北京时间视角）。

    北京时间凌晨 5:00 是美股收盘转换点：
    - 周六/周日 → 周五数据
    - 周一凌晨 5点前 → 周五数据
    - 周一凌晨 5点后 → 等待周一收盘（回补周五）
    - 周二凌晨 5点前 → 周一数据
    - 周二凌晨 5点后 → 等待周二收盘（回补周一）

    Returns:
        美股最近已收盘的交易日日期
    """
    from datetime import datetime
    import time

    now = datetime.now()
    weekday = now.weekday()  # 0=周一, 5=周六, 6=周日
    hour = now.hour

    # 周六、周日：回补周五
    if weekday == 5 or weekday == 6:
        # 往回找周五
        days_back = weekday - 4 if weekday == 5 else 2
        return (now - timedelta(days=days_back)).date()

    # 周一凌晨5点前：回补周五
    if weekday == 0 and hour < 5:
        return (now - timedelta(days=3)).date()

    # 周一凌晨5点后及周二至周五：
    # 凌晨5点前 → 前一天数据
    # 凌晨5点后 → 等待当天收盘，回补前一天
    if hour < 5:
        return (now - timedelta(days=1)).date()
    else:
        # 当前交易日尚未收盘，回补前一天
        return (now - timedelta(days=1)).date()


def _test_aapl_data(target_date: date) -> tuple[Optional[pd.DataFrame], str]:
    """
    测试 AAPL 是否有目标日期数据，判断 yfinance 是否已更新

    Args:
        target_date: 目标交易日

    Returns:
        (DataFrame, status) 其中 status 为:
        - "ok": 有目标日期数据
        - "rate_limit": 被限速或无数据，需等待
        - "error": 其他错误
    """
    end_dt = target_date + timedelta(days=1)
    start_dt = target_date - timedelta(days=5)

    try:
        signal.signal(signal.SIGINT, signal.SIG_DFL)
        df = yf.download(
            tickers="AAPL",
            start=start_dt.strftime("%Y-%m-%d"),
            end=end_dt.strftime("%Y-%m-%d"),
            interval="1d",
            progress=False,
            timeout=30,
        )
        if df is None or df.empty:
            return None, "rate_limit"

        # 处理 MultiIndex 列名（单 ticker 也返回 MultiIndex）
        df = df.reset_index()
        if isinstance(df.columns, pd.MultiIndex):
            # 取第一层列名（Price 层）
            df.columns = df.columns.get_level_values(0)
        df.columns = [str(c).lower() for c in df.columns]

        # 索引重命名
        if "date" not in df.columns and "datetime" in df.columns:
            df = df.rename(columns={"datetime": "date"})
        if "date" not in df.columns and "index" in df.columns:
            df = df.rename(columns={"index": "date"})

        df["date"] = pd.to_datetime(df["date"]).dt.date
        if target_date in df["date"].values:
            return df, "ok"
        return None, "rate_limit"
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

    # 先用 AAPL 测试 yfinance 是否已更新最近数据
    last_trading = _last_us_trading_date()
    test_df, status = _test_aapl_data(last_trading)

    if status == "rate_limit":
        log.warning(f"[AAPL] yfinance 被限速或无数据，跳过本次增量更新，稍后重试")
        return {t: "error: rate_limit" for t in tickers}
    elif status == "error":
        log.warning(f"[AAPL] 测试请求失败，跳过本次增量更新")
        return {t: "error: test_failed" for t in tickers}

    log.info(f"[AAPL] yfinance 已有 {last_trading} 数据，开始批量下载")

    result = {}
    conn = get_conn()
    try:
        # 分离新 ticker 和已同步 ticker
        new_tickers = []
        pending_tickers = []  # 需要增量更新的 ticker
        pending_start = None

        for t in tickers:
            last = get_last_sync(conn, t, "price")
            if last is None:
                new_tickers.append(t)
            elif last < last_trading:
                # 只有未同步到最新交易日的 ticker 才需要更新
                start_dt = last + timedelta(days=1)
                pending_tickers.append(t)
                if pending_start is None or start_dt < pending_start:
                    pending_start = start_dt
            # 已同步到 last_trading 的 ticker 跳过

        # 新 ticker 回填历史
        if new_tickers:
            log.info(f"[batch] {len(new_tickers)} 新 ticker 需回填 {HISTORY_YEARS} 年历史")
            for i in range(0, len(new_tickers), YF_BATCH_SIZE):
                batch_new = new_tickers[i:i + YF_BATCH_SIZE]
                _download_and_save(conn, batch_new, None, result)
                if i + YF_BATCH_SIZE < len(new_tickers):
                    delay = YF_BATCH_DELAY_BASE + random.uniform(-YF_BATCH_DELAY_JITTER, YF_BATCH_DELAY_JITTER)
                    log.debug(f"[batch] 等待 {delay:.1f}s 后继续")
                    time.sleep(delay)

        # 待更新 ticker 增量同步
        if pending_tickers:
            log.info(f"[batch] {len(pending_tickers)} ticker 需增量更新（从 {pending_start} 到 {last_trading}）")
            for i in range(0, len(pending_tickers), YF_BATCH_SIZE):
                batch_pending = pending_tickers[i:i + YF_BATCH_SIZE]
                _download_and_save(conn, batch_pending, pending_start, result)
                if i + YF_BATCH_SIZE < len(pending_tickers):
                    delay = YF_BATCH_DELAY_BASE + random.uniform(-YF_BATCH_DELAY_JITTER, YF_BATCH_DELAY_JITTER)
                    log.debug(f"[batch] 等待 {delay:.1f}s 后继续")
                    time.sleep(delay)
        else:
            log.info(f"[batch] 所有 ticker 已同步到 {last_trading}，无需增量更新")

        return result
    finally:
        conn.close()


def _download_and_save(conn, tickers: List[str], start_date: Optional[date], result: Dict[str, str]) -> None:
    """下载一批 ticker 数据并保存到数据库"""
    if not tickers:
        return

    # start_date 为 None 表示新 ticker，从历史起点到最近收盘日
    if start_date is None:
        last_trading = _last_us_trading_date()
        start_date = last_trading - timedelta(days=365 * HISTORY_YEARS)

    # end_dt 设为最近收盘日 + 1 天（yfinance end 参数不包含该日期）
    last_trading = _last_us_trading_date()
    end_dt = last_trading + timedelta(days=1)
    yf_symbols = [_yf_symbol(t) for t in tickers]

    log.info(f"[batch] 下载 {len(tickers)} 只股票, 日期范围: {start_date} ~ {last_trading}")

    df = None
    last_exc = None
    for attempt in range(YF_RETRY_COUNT):
        try:
            # 允许 Ctrl+C 中断 yfinance curl_cffi 调用
            signal.signal(signal.SIGINT, signal.SIG_DFL)
            df = yf.download(
                tickers=yf_symbols,
                start=start_date.strftime("%Y-%m-%d"),
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
        for t in tickers:
            set_sync_error(conn, t, "price", msg)
            result[t] = f"error: {last_exc}"
        return

    top_level = set()
    if df is not None and not df.empty and isinstance(df.columns, pd.MultiIndex):
        top_level = set(df.columns.get_level_values(0))

    for t in tickers:
        yf_t = _yf_symbol(t)
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