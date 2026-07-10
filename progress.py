"""progress.py — 周期性进度日志（百分比+速率+ETA）。

算法沿用 futu_ingest/concurrency.py 此前 ticker_stream 内联实现；
此前 data/stock_updater_cn_tushare.py 等多处各写一份无 rate/ETA 的简化版，
本模块统一收敛，格式统一升级为含 rate/ETA。
"""
from __future__ import annotations

import logging
import time

log = logging.getLogger(__name__)


def format_duration(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m}m{s:02d}s" if m else f"{s}s"


def log_progress(
    i: int,
    total: int,
    t0: float,
    *,
    every: int = 50,
    context: str = "",
    extra: str = "",
) -> None:
    """每 every 次或到达 total 时打印一行周期进度日志。

    i: 已处理数（从1开始计数）；total: 总数；
    t0: time.monotonic() 起始时间戳（速率/ETA 基准）。
    """
    if total <= 0 or (i % every != 0 and i != total):
        return
    elapsed = time.monotonic() - t0
    rate = i / elapsed if elapsed else 0.0
    eta = (total - i) / rate if rate else 0.0
    pct = i * 100 // total
    suffix = f" {extra}" if extra else ""
    log.info(f"{context}{i}/{total} ({pct}%){suffix} | {rate:.1f}/s ETA {format_duration(eta)}")
