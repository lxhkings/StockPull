"""
sync_log.py — 同步状态追踪（跨家族业务模块）

管理 sync_log 表的读写：记录每个 ticker 的最后成功/失败同步状态。
业务规则：仅 ok 状态才更新 last_date；error 状态保留原 last_date。
"""

import logging
from datetime import date
from typing import Optional

from core.db_client import get_conn

log = logging.getLogger(__name__)


def get_last_sync(conn, ticker: str, data_type: str) -> Optional[date]:
    """获取 ticker 最后成功同步日期。若 sync_log 无 ok 记录，fallback 到 prices 表查最新日期。"""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT last_date FROM sync_log "
            "WHERE ticker=%s AND data_type=%s AND status='ok'",
            (ticker, data_type)
        )
        row = cur.fetchone()
        if row:
            return row[0]

        # Fallback: 从 prices 表查该 ticker 最新日期（用于 error 状态 ticker 恢复增量）
        if data_type == "price":
            cur.execute(
                "SELECT MAX(date) FROM prices WHERE ticker=%s",
                (ticker,)
            )
            row = cur.fetchone()
            return row[0] if row and row[0] else None

    return None


def set_sync_ok(conn, ticker: str, data_type: str,
                last_date: date, rows_added: int = 0):
    _upsert_sync_log(conn, ticker, data_type, last_date, rows_added, "ok", "")


def set_sync_error(conn, ticker: str, data_type: str, message: str):
    _upsert_sync_log(conn, ticker, data_type, date.today(), 0, "error", message[:500])


def _upsert_sync_log(conn, ticker, data_type, last_date, rows_added, status, message):
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO sync_log
              (ticker, data_type, last_date, rows_added, status, message)
            VALUES (%s,%s,%s,%s,%s,%s)
            ON DUPLICATE KEY UPDATE
              last_date  = IF(VALUES(status)='ok', VALUES(last_date), last_date),
              rows_added = VALUES(rows_added),
              last_run   = CURRENT_TIMESTAMP,
              status     = VALUES(status),
              message    = VALUES(message)
        """, (ticker, data_type, last_date, rows_added, status, message))
    conn.commit()
