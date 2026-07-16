"""
http_utils.py — HTTP 请求 + 速率限制 + 数据类型转换（纯组件，无业务状态）

提供：
- HTTP 请求重试机制
- 速率限制控制
- 数据类型转换工具
"""

import time
import logging
import threading
from typing import Optional, TypeVar

import pandas as pd
import requests

log = logging.getLogger(__name__)

T = TypeVar("T")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 常量
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DEFAULT_TIMEOUT = 30
DEFAULT_RETRY_COUNT = 3
DEFAULT_RETRY_DELAY = 10

HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json, */*",
}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HTTP 重试机制
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def fetch_with_retry(
    url: str,
    headers: Optional[dict] = None,
    timeout: int = DEFAULT_TIMEOUT,
    max_retries: int = DEFAULT_RETRY_COUNT,
    retry_delay: int = DEFAULT_RETRY_DELAY,
    context: str = "",
) -> Optional[requests.Response]:
    """
    带重试机制的 HTTP GET 请求

    Args:
        url: 请求地址
        headers: 请求头（默认使用 HTTP_HEADERS）
        timeout: 超时秒数
        max_retries: 最大重试次数
        retry_delay: 重试间隔秒数
        context: 日志上下文（如 ticker 名称）

    Returns:
        Response 对象，失败返回 None
    """
    headers = headers or HTTP_HEADERS
    prefix = f"[{context}] " if context else ""

    for attempt in range(max_retries):
        try:
            resp = requests.get(url, headers=headers, timeout=timeout)
            resp.raise_for_status()
            return resp
        except Exception as e:
            if attempt < max_retries - 1:
                log.warning(f"{prefix}第{attempt + 1}次请求失败，{retry_delay}秒后重试: {e}")
                time.sleep(retry_delay)
            else:
                log.error(f"{prefix}请求失败，已重试{max_retries}次: {url}")
                raise

    return None


def fetch_urls_sequentially(
    urls: list,
    headers: Optional[dict] = None,
    timeout: int = DEFAULT_TIMEOUT,
    context: str = "",
) -> Optional[requests.Response]:
    """
    按顺序尝试多个 URL，返回第一个成功的响应

    Args:
        urls: URL 列表（按优先级排序）
        headers: 请求头
        timeout: 超时秒数
        context: 日志上下文

    Returns:
        第一个成功响应的 Response 对象，全部失败返回 None
    """
    headers = headers or HTTP_HEADERS

    for url in urls:
        try:
            resp = requests.get(url, headers=headers, timeout=timeout)
            resp.raise_for_status()
            return resp
        except Exception as e:
            log.warning(f"[{context}] {url[:50]} 失败: {e}")

    return None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 速率限制
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class RateLimiter:
    """简单的速率限制器"""

    def __init__(self, delay: float):
        self.delay = delay
        self._last_call = 0.0
        self._lock = threading.Lock()

    def wait(self):
        """等待直到可以执行下一次调用（线程安全：同一 limiter 的调用串行）"""
        with self._lock:
            elapsed = time.time() - self._last_call
            if elapsed < self.delay:
                time.sleep(self.delay - elapsed)
            self._last_call = time.time()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 数据转换工具
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def to_float(value) -> Optional[float]:
    """
    安全转换为 float

    Args:
        value: 任意值

    Returns:
        float 或 None
    """
    if value is None:
        return None
    try:
        f = float(value)
        return f if str(value) != "nan" else None
    except (ValueError, TypeError):
        return None


def to_int(value) -> Optional[int]:
    """
    安全转换为 int

    Args:
        value: 任意值

    Returns:
        int 或 None
    """
    f = to_float(value)
    return int(f) if f is not None else None


def or_none(value):
    """缺失值（None / NaN / NaT / pd.NA）→ None；其余原样返回。

    仅处理标量。调用方勿传入整表。
    """
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value

def to_date(value) -> Optional[str]:
    """
    YYYYMMDD 字符串/数值 → YYYY-MM-DD

    Args:
        value: tushare 返回的日期字段（YYYYMMDD 字符串、int、NaN、None 均可能出现）

    Returns:
        YYYY-MM-DD 字符串；None/NaN/空字符串输入返回 None；非 8 位字符串原样返回
    """
    if pd.isna(value) or value in (None, ""):
        return None
    s = str(value)
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}" if len(s) == 8 else s

def format_cik(cik) -> Optional[str]:
    """
    格式化 CIK 为 10 位数字字符串

    Args:
        cik: 原始 CIK 值

    Returns:
        10 位 CIK 字符串或 None
    """
    if cik is None or str(cik) in ("nan", "None", ""):
        return None
    try:
        return str(int(cik)).zfill(10)
    except (ValueError, TypeError):
        return None
