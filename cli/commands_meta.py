"""Meta CLI commands: init, status."""

from __future__ import annotations


def cmd_init() -> int:
    from core.db_client import execute
    from config import INDEX_CONFIG
    rows = [
        (idx, cfg["name"], cfg["etf"], cfg["description"])
        for idx, cfg in INDEX_CONFIG.items()
    ]
    n = execute(
        "INSERT IGNORE INTO indices (index_id, name, etf_ticker, description) "
        "VALUES (%s,%s,%s,%s)",
        rows, many=True,
    )
    print(f"init: inserted {n} new rows into `indices` (existing rows unchanged)")
    return 0


def cmd_status() -> int:
    from modules.db_admin import show_status
    show_status()
    return 0
