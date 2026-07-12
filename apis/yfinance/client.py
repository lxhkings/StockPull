"""yf_client.py — yfinance 请求封装（限速+重试层）。

对齐 apis.tushare/client.py、apis.futu/client.py 的模块结构：所有 yf.download
调用统一走这里，指数退避重试通过 retry_utils.retry_with_backoff 实现。
"""
from __future__ import annotations

import logging
import signal
from typing import Optional

import pandas as pd
import yfinance as yf

from config import YF_RETRY_COUNT, YF_TIMEOUT, YF_THREADS
from core.retry_utils import retry_with_backoff

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

    def _call():
        # 允许 Ctrl+C 中断 yfinance curl_cffi 调用
        signal.signal(signal.SIGINT, signal.SIG_DFL)
        return yf.download(**kwargs)

    return retry_with_backoff(
        _call, retry_count=retry_count, base_delay=5, multiplier=3,
        context=f"{context}yf.download",
    )


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
    def _call():
        signal.signal(signal.SIGINT, signal.SIG_DFL)
        return yf.Ticker(ticker).history(start=start, end=end)

    return retry_with_backoff(
        _call, retry_count=retry_count, base_delay=5, multiplier=3,
        context=f"{context}yf.Ticker.history",
    )
