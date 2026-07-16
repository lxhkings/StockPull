"""Tushare CLI commands: sync/full/flush."""

from __future__ import annotations

from cli.commands_common import _run_buffered


def cmd_tushare_backfill(scope: str, market: str, dry_run: bool, start: str | None = None) -> int:
    """两阶段：backfill 写本地缓冲 → 自动 flush 到 NAS。flush 失败则保留缓冲、提示兜底。"""
    from apis.tushare.orchestrator import run_full_backfill
    from config import TUSHARE_BUFFER_PATH

    if dry_run:
        rep = run_full_backfill(scope=scope, market=market, dry_run=dry_run, start=start)
        print(rep.render())
        return 0

    return _run_buffered(
        TUSHARE_BUFFER_PATH,
        lambda: run_full_backfill(scope=scope, market=market, dry_run=False, start=start),
        done_label="BACKFILL ",
        flush_cmd="tushare flush",
    )


def cmd_tushare_full(scope: str, market: str, dry_run: bool) -> int:
    """全量强制回填：起点固定为 TUSHARE_BACKFILL_START，等价 tushare sync --start 2010起。"""
    from config import TUSHARE_BACKFILL_START
    return cmd_tushare_backfill(scope, market, dry_run, start=TUSHARE_BACKFILL_START)


def cmd_tushare_flush(workers: int = 1) -> int:
    from core.local_buffer import flush, flush_parallel, pending_count
    from config import TUSHARE_BUFFER_PATH
    n = pending_count(TUSHARE_BUFFER_PATH)
    if n == 0:
        print("无待传数据。")
        return 0
    if workers > 1:
        print(f"待传 {n} 条，开始 flush -> NAS (并发 {workers}) ...")
        print(flush_parallel(TUSHARE_BUFFER_PATH, workers=workers))
    else:
        print(f"待传 {n} 条，开始 flush -> NAS ...")
        print(flush(TUSHARE_BUFFER_PATH))
    return 0
