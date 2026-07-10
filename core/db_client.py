"""
db_client.py — 数据库连接组件（纯连接，无业务状态）

提供连接池化的 get_conn + query/execute 工具函数。
连接池基于 DBUtils.PooledDB，线性退避重试。
"""

import time
import logging
from typing import List, Dict

import pymysql
import pymysql.cursors
from dbutils.pooled_db import PooledDB

from config import (
    DB,
    DB_CONNECT_RETRIES,
    DB_CONNECT_BACKOFF,
    DB_POOL_MAX_CONNECTIONS,
    DB_POOL_MIN_CACHED,
    DB_POOL_MAX_CACHED,
    FUTU_BUFFER_PATH,
)

log = logging.getLogger(__name__)

_local_first = False
_local_buffer_path = FUTU_BUFFER_PATH

_pool = None


def _get_pool() -> PooledDB:
    """延迟创建连接池（首次调用 get_conn 时才初始化）。"""
    global _pool
    if _pool is None:
        _pool = PooledDB(
            creator=pymysql,
            maxconnections=DB_POOL_MAX_CONNECTIONS,
            mincached=DB_POOL_MIN_CACHED,
            maxcached=DB_POOL_MAX_CACHED,
            blocking=True,
            ping=1,
            setsession=["SET time_zone = '+08:00'"],
            **DB,
        )
    return _pool


def set_local_first(on: bool, buffer_path: str | None = None) -> None:
    """开/关本地优先模式。开启后 get_conn 返回 BufferingConnection（写入本地缓冲）。

    buffer_path 未传时沿用上次设置的路径（默认 FUTU_BUFFER_PATH，向后兼容 futu 的既有调用）；
    tushare 等其他调用方应显式传自己的缓冲路径（如 TUSHARE_BUFFER_PATH），避免和 futu 混用同一份缓冲。
    """
    global _local_first, _local_buffer_path
    _local_first = on
    if buffer_path is not None:
        _local_buffer_path = buffer_path


def get_conn() -> pymysql.Connection:
    """获取数据库连接（池化，线性退避重试）。

    本地优先模式下返回 BufferingConnection：写入本地缓冲，读透传 NAS。
    """
    if _local_first:
        from core.local_buffer import BufferingConnection
        return BufferingConnection(_local_buffer_path, DB)

    last: Exception = RuntimeError("DB_CONNECT_RETRIES must be >= 1")
    for attempt in range(1, DB_CONNECT_RETRIES + 1):
        try:
            return _get_pool().connection()
        except pymysql.err.OperationalError as e:
            last = e
            if attempt < DB_CONNECT_RETRIES:
                log.warning(f"DB connect failed ({attempt}/{DB_CONNECT_RETRIES}): {e}; "
                            f"retry in {DB_CONNECT_BACKOFF * attempt}s")
                time.sleep(DB_CONNECT_BACKOFF * attempt)
    raise last


def query(sql: str, params=None) -> List[Dict]:
    """
    执行 SELECT 并返回 list[dict]
    避免 pd.read_sql 的 backtick/format 问题
    """
    conn = get_conn()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cur:
            cur.execute(sql, params or ())
            return cur.fetchall()
    finally:
        conn.close()


def execute(sql: str, params=None, many: bool = False) -> int:
    """执行 INSERT/UPDATE/DELETE，返回影响行数"""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            if many:
                cur.executemany(sql, params or [])
            else:
                cur.execute(sql, params or ())
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()
