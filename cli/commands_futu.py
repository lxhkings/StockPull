"""Futu CLI commands: full/sync/flush."""

from __future__ import annotations

from cli.commands_common import _run_buffered


def _run_futu(scope: str, force: bool) -> int:
    from apis.futu.orchestrator import run_sync
    from config import FUTU_BUFFER_PATH

    return _run_buffered(
        FUTU_BUFFER_PATH,
        lambda: run_sync(scope=scope, force=force),
        done_label="FETCH ",
        flush_cmd="futu flush",
    )


def cmd_futu_full(scope: str) -> int:
    return _run_futu(scope, force=True)


def cmd_futu_sync(scope: str) -> int:
    return _run_futu(scope, force=False)


def cmd_futu_flush() -> int:
    from core.local_buffer import flush, pending_count
    from config import FUTU_BUFFER_PATH
    n = pending_count(FUTU_BUFFER_PATH)
    if n == 0:
        print("无待传数据。")
        return 0
    print(f"待传 {n} 条，开始 flush -> NAS ...")
    print(flush(FUTU_BUFFER_PATH))
    return 0
