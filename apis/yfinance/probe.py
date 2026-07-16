"""AAPL readiness probes for yfinance US feeds. Status: ok|no_data|rate_limit|error."""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Optional

import pandas as pd

from config import YF_TIMEOUT
from apis.yfinance.client import download_with_retry
from apis.yfinance.normalize import lower_ohlc_columns

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


def _is_rate_limit(exc: BaseException) -> bool:
    msg = str(exc)
    return "RateLimit" in msg or "Too Many Requests" in msg


def _probe_has_date(
    *,
    interval: str,
    start: date,
    end: date,
    target: date,
    context: str,
) -> str:
    """Download AAPL OHLCV window; return ok if target date present."""
    try:
        df = download_with_retry(
            tickers="AAPL",
            start=start.strftime("%Y-%m-%d"),
            end=end.strftime("%Y-%m-%d"),
            interval=interval,
            group_by="column",
            threads=False,
            timeout=YF_TIMEOUT,
            context=context,
        )
        if df is None or df.empty:
            return "no_data"

        df = lower_ohlc_columns(df.reset_index())
        if "date" not in df.columns:
            for cand in ("datetime", "index"):
                if cand in df.columns:
                    df = df.rename(columns={cand: "date"})
                    break
        if "date" not in df.columns:
            return "no_data"

        dates = pd.to_datetime(df["date"]).dt.date
        if target in set(dates):
            return "ok"
        return "no_data"
    except Exception as e:
        if _is_rate_limit(e):
            log.warning(f"{context}yfinance 被限速: {e}")
            return "rate_limit"
        log.warning(f"{context}测试请求失败: {e}")
        return "error"


def probe_daily(target_date: date) -> str:
    """Test whether yfinance has daily bars for target_date (AAPL probe)."""
    end_dt = target_date + timedelta(days=1)
    start_dt = target_date - timedelta(days=5)
    return _probe_has_date(
        interval="1d",
        start=start_dt,
        end=end_dt,
        target=target_date,
        context="[AAPL probe] ",
    )


def probe_weekly(target_monday: date) -> str:
    """Test whether yfinance has weekly bar for week starting target_monday."""
    start = target_monday - timedelta(days=14)
    end = target_monday + timedelta(days=7)
    return _probe_has_date(
        interval="1wk",
        start=start,
        end=end,
        target=target_monday,
        context="[AAPL weekly probe] ",
    )


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
        if _is_rate_limit(e):
            log.warning(f"[AAPL {interval}] yfinance 被限速: {e}")
            return None, "rate_limit"
        log.error(f"[AAPL {interval}] 测试失败: {e}")
        return None, "error"
