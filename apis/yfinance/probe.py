"""AAPL readiness probes for yfinance US feeds. Status: ok|no_data|rate_limit|error."""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Optional

import pandas as pd

from config import YF_TIMEOUT
from apis.yfinance.client import download_with_retry

log = logging.getLogger(__name__)

# interval → yfinance 参数字符串（probe + prices_intraday 共用）
YF_INTERVAL_MAP: dict[str, str] = {
    "15m": "15m",
    "1h": "60m",
}

# interval → yfinance 免费 tier 最大可拉天数
INTERVAL_LOOKBACK_DAYS: dict[str, int] = {
    "15m": 60,
    "1h": 730,
}


def probe_daily(target_date: date) -> tuple[Optional[pd.DataFrame], str]:
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


def probe_weekly(target_monday: date) -> tuple[Optional[pd.DataFrame], str]:
    """Test if yfinance has weekly data for the week starting target_monday.

    Returns:
        (DataFrame, status) 其中 status 为:
        - "ok": 有目标周一数据
        - "rate_limit": 被限速
        - "error": 其他错误
        - "no_data": 空/无目标周
    """
    start = target_monday - timedelta(days=14)
    end = target_monday + timedelta(days=7)
    try:
        df = download_with_retry(
            tickers="AAPL",
            start=start.strftime("%Y-%m-%d"),
            end=end.strftime("%Y-%m-%d"),
            interval="1wk",
            group_by="column",
            threads=False,
            timeout=30,
            context="[AAPL weekly probe] ",
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


def probe_intraday(interval: str) -> tuple[Optional[date], str]:
    """
    测试 AAPL 是否有最近交易日数据，判断 yfinance intraday API 是否可用

    Returns:
        (latest_date, status) 其中 status 为:
        - "ok": 有数据，返回最新日期
        - "no_data": 无数据（周末/假期或未更新）
        - "rate_limit": 被限速
        - "error": 其他错误
    """
    try:
        today = date.today()
        floor = today - timedelta(days=INTERVAL_LOOKBACK_DAYS[interval] - 1)
        end = today + timedelta(days=1)

        df = download_with_retry(
            tickers="AAPL",
            start=floor.strftime("%Y-%m-%d"),
            end=end.strftime("%Y-%m-%d"),
            interval=YF_INTERVAL_MAP[interval],
            group_by="ticker",
            threads=False,
            timeout=YF_TIMEOUT,
            context=f"[AAPL {interval} probe] ",
        )

        if df is None or df.empty:
            return None, "no_data"

        latest = df.index[-1].date()
        log.info(f"[AAPL {interval}] 测试成功：最新日期 {latest}，范围 {floor} ~ {latest}")
        return latest, "ok"

    except Exception as e:
        err_msg = str(e)
        if "RateLimit" in err_msg or "Too Many Requests" in err_msg:
            log.warning(f"[AAPL {interval}] yfinance 被限速: {e}")
            return None, "rate_limit"
        log.error(f"[AAPL {interval}] 测试失败: {e}")
        return None, "error"
