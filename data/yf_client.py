"""yf_client.py — yfinance 请求封装（限速+重试层）。

对齐 ts_ingest/client.py、futu_ingest/client.py 的模块结构：所有 yf.download
调用统一走这里，指数退避重试（5 * 3**attempt 秒）。此前该重试逻辑在
stock_updater_us.py / stock_updater_us_weekly.py / intraday_updater_us.py
里各自重复实现了一份。
"""
from __future__ import annotations

import logging
import signal
import time
from typing import Optional

import pandas as pd
import yfinance as yf

from config import YF_RETRY_COUNT, YF_TIMEOUT, YF_THREADS

log = logging.getLogger(__name__)


def download_with_retry(
    tickers,
    start: str,
    end: str,
    interval: str,
    *,
    group_by: str = "ticker",
    threads=YF_THREADS,
    repair: Optional[bool] = None,
    timeout: int = YF_TIMEOUT,
    retry_count: int = YF_RETRY_COUNT,
    context: str = "",
) -> pd.DataFrame:
    """yf.download 封装：指数退避重试，耗尽后抛出最后一次异常。

    Args:
        context: 日志前缀（如 "[batch] "），用于区分调用来源
    """
    kwargs = dict(
        tickers=tickers, start=start, end=end, interval=interval,
        group_by=group_by, auto_adjust=False, actions=False,
        threads=threads, progress=False, timeout=timeout,
    )
    if repair is not None:
        kwargs["repair"] = repair

    last_exc: Optional[Exception] = None
    for attempt in range(retry_count):
        try:
            # 允许 Ctrl+C 中断 yfinance curl_cffi 调用
            signal.signal(signal.SIGINT, signal.SIG_DFL)
            return yf.download(**kwargs)
        except Exception as e:
            last_exc = e
            if attempt < retry_count - 1:
                backoff = 5 * (3 ** attempt)
                log.warning(f"{context}yf.download 第 {attempt + 1} 次失败，{backoff}s 后重试: {e}")
                time.sleep(backoff)

    raise last_exc


def history_with_retry(
    ticker: str,
    start: str,
    end: str,
    *,
    retry_count: int = YF_RETRY_COUNT,
    context: str = "",
) -> pd.DataFrame:
    """yf.Ticker(ticker).history() 封装：指数退避重试，耗尽后抛出最后一次异常。

    与 download_with_retry 分开是因为 yf.Ticker().history() 走单独的 auto_adjust
    默认行为（HK 复权价依赖这个默认值，不能改走 yf.download）。
    """
    last_exc: Optional[Exception] = None
    for attempt in range(retry_count):
        try:
            signal.signal(signal.SIGINT, signal.SIG_DFL)
            return yf.Ticker(ticker).history(start=start, end=end)
        except Exception as e:
            last_exc = e
            if attempt < retry_count - 1:
                backoff = 5 * (3 ** attempt)
                log.warning(f"{context}yf.Ticker.history 第 {attempt + 1} 次失败，{backoff}s 后重试: {e}")
                time.sleep(backoff)

    raise last_exc
