"""Futu OpenQuoteContext 单例封装。

每次 call 自动：
- 阻塞到满足 FUTU_RATE_INTERVAL（限频）
- ret != RET_OK 时按 FUTU_RETRY_DELAY 指数退避（最多 FUTU_RETRY_COUNT 次）
- 全部失败抛 RuntimeError
"""
from __future__ import annotations

import logging
import socket
import time
from functools import lru_cache

from config import (
    FUTU_OPEND_HOST, FUTU_OPEND_PORT, FUTU_RATE_INTERVAL,
    FUTU_RETRY_COUNT, FUTU_RETRY_DELAY,
)
from data.base import RateLimiter

log = logging.getLogger(__name__)

RET_OK = 0   # futu.RET_OK 的实际值


def to_futu_code(ticker: str) -> str:
    """canonical 美股 ticker -> Futu 代码。AAPL -> US.AAPL"""
    return f"US.{ticker}"


def from_futu_code(code: str) -> str:
    """Futu 代码 -> canonical。US.AAPL -> AAPL"""
    return code[3:] if code.startswith("US.") else code


def _check_opend(host: str, port: int) -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(2)
    try:
        sock.connect((host, port))
    except OSError as e:
        raise RuntimeError(
            f"无法连接 OpenD ({host}:{port}): {e}。请先启动 OpenD 客户端。"
        ) from e
    finally:
        sock.close()


class FutuClient:
    def __init__(self):
        self._ctx = None
        self._limiter = RateLimiter(FUTU_RATE_INTERVAL)

    def _ensure_ctx(self):
        if self._ctx is None:
            _check_opend(FUTU_OPEND_HOST, FUTU_OPEND_PORT)
            from futu import OpenQuoteContext
            self._ctx = OpenQuoteContext(host=FUTU_OPEND_HOST, port=FUTU_OPEND_PORT)
        return self._ctx

    def call(self, method_name: str, *args, **kwargs):
        """调用 ctx.<method_name>(*args, **kwargs)，返回 data（ret 校验在内部）。"""
        ctx = self._ensure_ctx()
        last_err = None
        for attempt in range(FUTU_RETRY_COUNT):
            self._limiter.wait()
            try:
                result = getattr(ctx, method_name)(*args, **kwargs)
                # 适配 3 值返回 (short_interest/daily_short_volume)
                if isinstance(result, tuple) and len(result) == 3:
                    ret, data, _ = result
                else:
                    ret, data = result
                if ret == RET_OK:
                    return data
                last_err = RuntimeError(f"futu.{method_name} ret={ret}: {data}")
            except Exception as e:  # noqa: BLE001
                last_err = e
            # 永久性错误（如"不支持"）不重试
            if "不支持" in str(last_err):
                raise last_err
            wait = FUTU_RETRY_DELAY * (2 ** attempt)
            log.warning(f"futu.{method_name} failed (attempt {attempt+1}): {last_err}; sleep {wait}s")
            time.sleep(wait)
        assert last_err is not None
        raise last_err

    def close(self):
        if self._ctx is not None:
            try:
                self._ctx.close()
            except Exception:  # noqa: BLE001
                pass
            self._ctx = None


@lru_cache(maxsize=1)
def get_client() -> FutuClient:
    return FutuClient()
