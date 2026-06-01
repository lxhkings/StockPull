"""跨接口并发原语。每接口一 worker 线程，共享单 ctx（接口限频桶独立）。"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable

log = logging.getLogger(__name__)


def ticker_stream(backfill_fn, client, tickers: list[str], label: str) -> tuple[int, int]:
    """单接口扫全部 ticker。返回 (总行数, ok 数)。单 ticker 异常被吞并 log。"""
    rows = ok = 0
    for t in tickers:
        try:
            rows += backfill_fn(client, t)
            ok += 1
        except Exception as e:  # noqa: BLE001
            log.error(f"{label} {t}: {e}")
    return rows, ok


def run_streams(streams: list[tuple[str, Callable[[], tuple[int, int]]]]) -> dict:
    """streams: [(key, fn)]，fn()->(rows, ok)。并发跑，返回 {key:(rows,ok)}。"""
    with ThreadPoolExecutor(max_workers=len(streams)) as ex:
        futs = {ex.submit(fn): key for key, fn in streams}
        return {futs[f]: f.result() for f in as_completed(futs)}
