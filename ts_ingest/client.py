"""Tushare Pro SDK 单例 + 限速 + 重试 + 调用计数。

每次 call 自动：
- 阻塞到满足 TUSHARE_RATE_INTERVAL（限速）
- 失败时按 TUSHARE_RETRY_DELAY 指数退避（最多 TUSHARE_RETRY_COUNT 次），
  经 retry_utils.retry_with_backoff 实现
- 调用 budget.tick() 累加计数
"""
from __future__ import annotations

import logging
from functools import lru_cache

import pandas as pd
import tushare as ts

from config import (
    TUSHARE_TOKEN,
    TUSHARE_RATE_INTERVAL,
    TUSHARE_RETRY_COUNT,
    TUSHARE_RETRY_DELAY,
)
from data.base import RateLimiter
from core.retry_utils import retry_with_backoff
from ts_ingest import budget

log = logging.getLogger(__name__)


class TushareClient:
    def __init__(self, pro):
        self._pro = pro
        self._limiter = RateLimiter(TUSHARE_RATE_INTERVAL)

    def call(self, api_name: str, **kwargs) -> pd.DataFrame:
        def _call():
            self._limiter.wait()
            fn = getattr(self._pro, api_name)
            df = fn(**kwargs)
            budget.tick(api_name)
            return df if df is not None else pd.DataFrame()

        return retry_with_backoff(
            _call, retry_count=TUSHARE_RETRY_COUNT, base_delay=TUSHARE_RETRY_DELAY,
            multiplier=2, context=f"tushare.{api_name}",
        )

    # 便利属性：直接拿 pro_bar（不走 pro_api 路径）
    def pro_bar(self, **kwargs) -> pd.DataFrame:
        def _call():
            self._limiter.wait()
            df = ts.pro_bar(**kwargs)
            budget.tick("pro_bar")
            return df if df is not None else pd.DataFrame()

        return retry_with_backoff(
            _call, retry_count=TUSHARE_RETRY_COUNT, base_delay=TUSHARE_RETRY_DELAY,
            multiplier=2, context="tushare.pro_bar",
        )


@lru_cache(maxsize=1)
def get_client() -> TushareClient:
    if not TUSHARE_TOKEN:
        raise RuntimeError("TUSHARE_TOKEN missing in .env")
    ts.set_token(TUSHARE_TOKEN)
    pro = ts.pro_api()
    return TushareClient(pro)
