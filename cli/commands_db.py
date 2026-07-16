"""DB admin CLI commands: migrate-intraday, purge-index."""

from __future__ import annotations


def cmd_migrate_intraday() -> int:
    from modules.db_admin import create_prices_intraday_table
    create_prices_intraday_table()
    print("prices_intraday table ready")
    return 0


def cmd_purge_index(index_id: str, yes: bool = False) -> int:
    """清理某 index_id 在指数相关表中的行。默认 dry-run，--yes 才 DELETE。"""
    from modules.db_admin import purge_index

    if not yes:
        counts = purge_index(index_id, dry_run=True)
        total = sum(counts.values())
        print(f"[dry-run] index_id={index_id!r} 各表行数（合计 {total}）：")
        for table, n in counts.items():
            print(f"  {table}: {n}")
        if total == 0:
            print("无数据，无需清理。")
        else:
            print(f"确认删除请加 --yes：uv run main.py db purge-index --index-id {index_id} --yes")
        return 0

    deleted = purge_index(index_id, dry_run=False)
    total = sum(deleted.values())
    print(f"[deleted] index_id={index_id!r} 合计 {total} 行：")
    for table, n in deleted.items():
        print(f"  {table}: {n}")
    return 0
