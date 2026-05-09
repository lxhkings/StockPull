"""A-share daily-K updater via akshare (后复权 / hfq).

Mirrors stock_system/data/stock_updater_us.py but uses akshare
stock_zh_a_hist instead of yfinance.

Flow per ticker:
  1. check last sync date (sync_log)
  2. fetch hfq daily bars from akshare
  3. INSERT IGNORE into prices table
  4. update sync_log
"""

from __future__ import annotations

import logging
import time
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

import akshare as ak
import pandas as pd

from config import (
    AKSHARE_RETRY_COUNT,
    AKSHARE_RETRY_DELAY,
    AKSHARE_REQUEST_DELAY,
    HISTORY_YEARS_CN,
)
from db import get_conn, get_last_sync, set_sync_ok, set_sync_error
from data.ticker_utils import to_akshare_a

log = logging.getLogger(__name__)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 单只入口
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def update_prices(ticker: str) -> None:
    """单只 ticker 增量更新"""
    update_prices_batch([ticker])


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 批量入口 (pipeline 用)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def update_prices_batch(tickers: List[str]) -> Dict[str, str]:
    """
    批量增量拉取一组 A-share ticker 的行情，写入 prices 表

    Args:
        tickers: canonical ticker 列表 (如 ["600519.SH", "000001.SZ"])

    Returns:
        {ticker: "ok" | "skipped" | "no_data" | "error: <msg>"}
    """
    if not tickers:
        return {}

    conn = get_conn()
    try:
        result: Dict[str, str] = {}

        for t in tickers:
            try:
                last = get_last_sync(conn, t, "price")
                if last == date.today():
                    result[t] = "skipped"
                    log.info(f"[{t}] 今日已同步，跳过")
                    continue

                if last is None:
                    start_dt = (
                        datetime.today() - timedelta(days=365 * HISTORY_YEARS_CN)
                    ).strftime("%Y%m%d")
                else:
                    start_dt = (last - timedelta(days=7)).strftime("%Y%m%d")

                end_dt = datetime.today().strftime("%Y%m%d")
                df = _fetch_prices_cn(t, start_dt, end_dt)

                if df is None or df.empty:
                    set_sync_error(conn, t, "price", "akshare: 无数据")
                    result[t] = "no_data"
                    continue

                rows_inserted = _save_prices(conn, t, df)
                new_last = df["date"].max()
                set_sync_ok(conn, t, "price", new_last, rows_inserted)
                result[t] = "ok"
                log.info(f"[{t}] 写入 {rows_inserted} 条，最新={new_last}")

                time.sleep(AKSHARE_REQUEST_DELAY)

            except Exception as e:
                log.error(f"[{t}] 更新失败: {e}")
                set_sync_error(conn, t, "price", str(e))
                result[t] = f"error: {e}"

        return result
    finally:
        conn.close()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 内部工具
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _fetch_prices_cn(
    ticker: str, start: str, end: str
) -> Optional[pd.DataFrame]:
    """
    从 akshare 拉取单只 A-share 后复权日线

    Args:
        ticker: canonical 形式 (如 "600519.SH")
        start:  "YYYYMMDD"
        end:    "YYYYMMDD"

    Returns:
        DataFrame [date, open, high, low, close, volume] 或 None
    """
    code = to_akshare_a(ticker)
    last_exc = None

    for attempt in range(AKSHARE_RETRY_COUNT):
        try:
            raw = ak.stock_zh_a_hist(
                symbol=code,
                period="daily",
                start_date=start,
                end_date=end,
                adjust="hfq",
            )
            if raw is None or raw.empty:
                return None

            df = pd.DataFrame({
                "date":   pd.to_datetime(raw["日期"]).dt.date,
                "open":   raw["开盘"].astype(float),
                "high":   raw["最高"].astype(float),
                "low":    raw["最低"].astype(float),
                "close":  raw["收盘"].astype(float),
                "volume": raw["成交量"].astype(float),
            })
            return df

        except Exception as e:
            last_exc = e
            if attempt < AKSHARE_RETRY_COUNT - 1:
                log.warning(
                    f"[{ticker}] 第{attempt+1}次失败，{AKSHARE_RETRY_DELAY}s 后重试: {e}"
                )
                time.sleep(AKSHARE_RETRY_DELAY)

    log.error(f"[{ticker}] akshare 拉取失败: {last_exc}")
    return None


def _save_prices(conn, ticker: str, df: pd.DataFrame) -> int:
    """INSERT IGNORE 写 prices 表"""
    sql = """
        INSERT IGNORE INTO prices (ticker, date, open, high, low, close, volume)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """
    rows = [
        (
            ticker,
            r.date,
            r.open,
            r.high,
            r.low,
            r.close,
            int(r.volume) if r.volume == r.volume else None,  # NaN check
        )
        for r in df.itertuples(index=False)
    ]
    with conn.cursor() as cur:
        cur.executemany(sql, rows)
    conn.commit()
    return len(rows)
