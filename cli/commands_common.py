"""Shared helpers for CLI command modules."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


def _format_run_result(result: Any) -> str:
    render = getattr(result, "render", None)
    if callable(render):
        return render()
    return str(result)


def _run_buffered(
    buffer_path: str,
    run_fn: Callable[[], Any],
    *,
    done_label: str,
    flush_cmd: str,
) -> int:
    """本地缓冲两阶段：set_local_first → run_fn → flush。flush 失败保留缓冲。"""
    from core.db_client import set_local_first
    from core.local_buffer import flush, pending_count

    set_local_first(True, buffer_path=buffer_path)
    try:
        result = run_fn()
    finally:
        set_local_first(False)

    print(_format_run_result(result))

    try:
        fstat = flush(buffer_path)
        print(f"flush -> NAS: {fstat}")
    except Exception as e:  # noqa: BLE001
        n = pending_count(buffer_path)
        print(
            f"{done_label}完成并已存本地。FLUSH 失败: {e}\n"
            f"缓冲 {n} 条待传保留。NAS 恢复后跑: uv run main.py {flush_cmd}"
        )
        return 1
    return 0


def _import_market(market: str):
    if market == "us":
        from jobs import market_us as m
    elif market == "cn":
        from jobs import market_cn as m
    elif market == "hk":
        from jobs import market_hk as m
    else:
        raise ValueError(market)
    return m
