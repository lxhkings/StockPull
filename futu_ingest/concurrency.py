"""跨接口并发原语。每接口一 worker 线程，共享单 ctx（接口限频桶独立）。"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable

from tqdm import tqdm

from config import FUTU_REFRESH_DAYS, FUTU_DEFAULT_REFRESH_DAYS
from futu_ingest.client import PERMANENT_ERRORS
from futu_ingest.sync import fresh_tickers, mark_ok, mark_error, mark_skip

log = logging.getLogger(__name__)


def ticker_stream(backfill_fn, client, tickers: list[str], data_type: str,
                  force: bool = False) -> tuple[int, int, int]:
    """单接口扫全部 ticker，按 data_type 节流。返回 (总行数, ok 数, 跳过数)。

    force=False 时跳过 sync_log 中仍新鲜（< refresh_days）的 ticker，完全不调 API。
    单 ticker 异常被吞、记 sync_log error 并 log。
    """
    refresh_days = FUTU_REFRESH_DAYS.get(data_type, FUTU_DEFAULT_REFRESH_DAYS)
    fresh = set() if force else fresh_tickers(data_type, refresh_days)
    todo = [t for t in tickers if t not in fresh]
    total = len(todo)
    skipped = len(tickers) - total          # fresh 跳过先计入
    rows = ok = err = 0
    log.info(f"{data_type}: 待采 {total}, fresh跳过 {skipped}")
    pbar = tqdm(todo, desc=data_type, unit="ticker")
    for t in pbar:
        try:
            n = backfill_fn(client, t)
            mark_ok(t, data_type, n)
            rows += n
            ok += 1
        except Exception as e:  # noqa: BLE001
            # 永久错误（富途无此票/接口不支持该类型，如 REIT）标记跳过，不再每 run 重试
            if any(m in str(e) for m in PERMANENT_ERRORS):
                log.warning(f"{data_type} {t}: 永久不支持，标记跳过 ({e})")
                mark_skip(t, data_type)
                skipped += 1
            else:
                log.error(f"{data_type} {t}: {e}")
                mark_error(t, data_type, str(e))
                err += 1
        pbar.set_postfix(ok=ok, skip=skipped, err=err)
    return rows, ok, skipped


def batch_with_bisect(client, method: str, codes: list[str], *args, **kwargs) -> list:
    """批量调 client.call(method, codes, ...)。整批因单个"未知股票"失败时二分隔离，
    跳过坏 code、保留好 code。返回成功调用的 data 列表（调用方自行解析/落库）。

    非"未知股票"异常照常抛出（真错误应暴露）。batch 接口的容错原语，
    对应 ticker_stream 之于单票接口。
    """
    if not codes:
        return []
    try:
        return [client.call(method, codes, *args, **kwargs)]
    except RuntimeError as e:
        if not any(m in str(e) for m in PERMANENT_ERRORS):
            raise
        if len(codes) == 1:
            log.warning(f"{method} 跳过不支持的票 {codes[0]}")
            return []
        mid = len(codes) // 2
        return (batch_with_bisect(client, method, codes[:mid], *args, **kwargs)
                + batch_with_bisect(client, method, codes[mid:], *args, **kwargs))


def run_streams(streams: list[tuple[str, Callable[[], tuple[int, int]]]]) -> dict:
    """streams: [(key, fn)]，fn()->(rows, ok)。并发跑，返回 {key:(rows,ok)}。"""
    with ThreadPoolExecutor(max_workers=len(streams)) as ex:
        futs = {ex.submit(fn): key for key, fn in streams}
        return {futs[f]: f.result() for f in as_completed(futs)}
