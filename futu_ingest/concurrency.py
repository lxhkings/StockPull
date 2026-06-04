"""跨接口并发原语。每接口一 worker 线程，共享单 ctx（接口限频桶独立）。"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable

from config import FUTU_REFRESH_DAYS, FUTU_DEFAULT_REFRESH_DAYS
from futu_ingest.sync import fresh_tickers, mark_ok, mark_error

log = logging.getLogger(__name__)


def ticker_stream(backfill_fn, client, tickers: list[str], data_type: str,
                  force: bool = False) -> tuple[int, int, int]:
    """单接口扫全部 ticker，按 data_type 节流。返回 (总行数, ok 数, 跳过数)。

    force=False 时跳过 sync_log 中仍新鲜（< refresh_days）的 ticker，完全不调 API。
    单 ticker 异常被吞、记 sync_log error 并 log。
    """
    refresh_days = FUTU_REFRESH_DAYS.get(data_type, FUTU_DEFAULT_REFRESH_DAYS)
    skip = set() if force else fresh_tickers(data_type, refresh_days)
    rows = ok = skipped = 0
    for t in tickers:
        if t in skip:
            skipped += 1
            continue
        try:
            n = backfill_fn(client, t)
            mark_ok(t, data_type, n)
            rows += n
            ok += 1
        except Exception as e:  # noqa: BLE001
            log.error(f"{data_type} {t}: {e}")
            mark_error(t, data_type, str(e))
    return rows, ok, skipped


def run_streams(streams: list[tuple[str, Callable[[], tuple[int, int]]]]) -> dict:
    """streams: [(key, fn)]，fn()->(rows, ok)。并发跑，返回 {key:(rows,ok)}。"""
    with ThreadPoolExecutor(max_workers=len(streams)) as ex:
        futs = {ex.submit(fn): key for key, fn in streams}
        return {futs[f]: f.result() for f in as_completed(futs)}
