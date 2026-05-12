"""Tushare Pro SDK 单例 + 限速 + 重试 + 调用计数。

每次 call 自动：
- 阻塞到满足 TUSHARE_RATE_INTERVAL（限速）
- 失败时按 TUSHARE_RETRY_DELAY 指数退避（最多 TUSHARE_RETRY_COUNT 次）
- 调用 budget.tick() 累加计数
"""
from __future__ import annotations

import logging
import time
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
from ts_ingest import budget

log = logging.getLogger(__name__)


class TushareClient:
    def __init__(self, pro):
        self._pro = pro
        self._limiter = RateLimiter(TUSHARE_RATE_INTERVAL)

    def call(self, api_name: str, **kwargs) -> pd.DataFrame:
        last_err: Exception | None = None
        for attempt in range(TUSHARE_RETRY_COUNT):
            self._limiter.wait()
            try:
                fn = getattr(self._pro, api_name)
                df = fn(**kwargs)
                budget.tick(api_name)
                return df if df is not None else pd.DataFrame()
            except Exception as e:
                last_err = e
                wait = TUSHARE_RETRY_DELAY * (2 ** attempt)
                log.warning(f"tushare.{api_name} failed (attempt {attempt+1}): {e}; sleep {wait}s")
                time.sleep(wait)
        assert last_err is not None
        raise last_err

    # 便利属性：直接拿 pro_bar（不走 pro_api 路径）
    def pro_bar(self, **kwargs) -> pd.DataFrame:
        last_err: Exception | None = None
        for attempt in range(TUSHARE_RETRY_COUNT):
            self._limiter.wait()
            try:
                df = ts.pro_bar(**kwargs)
                budget.tick("pro_bar")
                return df if df is not None else pd.DataFrame()
            except Exception as e:
                last_err = e
                wait = TUSHARE_RETRY_DELAY * (2 ** attempt)
                log.warning(f"tushare.pro_bar failed (attempt {attempt+1}): {e}; sleep {wait}s")
                time.sleep(wait)
        assert last_err is not None
        raise last_err


@lru_cache(maxsize=1)
def get_client() -> TushareClient:
    if not TUSHARE_TOKEN:
        raise RuntimeError("TUSHARE_TOKEN missing in .env")
    ts.set_token(TUSHARE_TOKEN)
    pro = ts.pro_api()
    return TushareClient(pro)
