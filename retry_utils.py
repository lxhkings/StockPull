"""retry_utils.py — 通用重试+指数退避骨架。

三家 client（yf_client.py / ts_ingest/client.py / futu_ingest/client.py）
此前各自实现了一份指数退避循环，本模块收敛为单一实现。
"""
from __future__ import annotations

import logging
import time
from typing import Callable, TypeVar

log = logging.getLogger(__name__)

T = TypeVar("T")


def retry_with_backoff(
    fn: Callable[[], T],
    *,
    retry_count: int,
    base_delay: float,
    multiplier: float = 2,
    should_retry: Callable[[Exception], bool] = lambda e: True,
    context: str = "",
) -> T:
    """调用 fn()，失败按 base_delay * multiplier**attempt 指数退避重试。

    should_retry(e) 返回 False 时立即 raise，不再重试（用于永久性错误短路）。
    重试耗尽后 raise 最后一次异常。最后一次失败不 sleep。
    """
    last_exc: Exception | None = None
    for attempt in range(retry_count):
        try:
            return fn()
        except Exception as e:
            last_exc = e
            if not should_retry(e):
                raise
            if attempt < retry_count - 1:
                wait = base_delay * (multiplier ** attempt)
                log.warning(f"{context} failed (attempt {attempt + 1}/{retry_count}): {e}; retry in {wait}s")
                time.sleep(wait)
    raise last_exc
