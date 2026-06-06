"""Futu 本地优先缓冲：抓取写本地 SQLite，flush 阶段重放到 NAS。

本地优先模式下 db.get_conn() 返回 BufferingConnection（鸭子类型兼容 pymysql）：
写(INSERT/REPLACE/UPDATE/DELETE)入本地 pending_writes；读(SELECT/SHOW/SET)透传真 NAS。
flush() 按 seq 顺序重放，幂等 upsert，每条成功即删（断点续传）。
"""
from __future__ import annotations

import json
import os
import sqlite3
import logging

import pymysql
import pymysql.cursors

log = logging.getLogger(__name__)

_WRITE_KEYWORDS = ("INSERT", "REPLACE", "UPDATE", "DELETE")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS pending_writes (
    seq     INTEGER PRIMARY KEY AUTOINCREMENT,
    sql     TEXT    NOT NULL,
    params  TEXT,
    is_many INTEGER NOT NULL,
    ts      TEXT    DEFAULT (datetime('now'))
)
"""


def _is_write(sql: str) -> bool:
    if not sql:
        return False
    parts = sql.lstrip().split(None, 1)
    head = parts[0].upper() if parts else ""
    return head in _WRITE_KEYWORDS


def _open_local(path: str) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute(_SCHEMA)
    conn.commit()
    return conn


class BufferingCursor:
    """游标代理：写入本地缓冲，读透传 NAS。"""

    def __init__(self, conn: "BufferingConnection", cursorclass=None):
        self._conn = conn
        self._cursorclass = cursorclass
        self._real_cur = None
        self.rowcount = -1

    def execute(self, sql, params=None):
        if _is_write(sql):
            self._conn._append(sql, params, is_many=False)
            self.rowcount = 1
        else:
            self._real_cur = self._conn._nas_cursor(self._cursorclass)
            self._real_cur.execute(sql, params)
            self.rowcount = self._real_cur.rowcount
        return self.rowcount

    def executemany(self, sql, seq_params):
        seq_params = list(seq_params)
        if _is_write(sql):
            self._conn._append(sql, seq_params, is_many=True)
            self.rowcount = len(seq_params)
        else:
            self._real_cur = self._conn._nas_cursor(self._cursorclass)
            self._real_cur.executemany(sql, seq_params)
            self.rowcount = self._real_cur.rowcount
        return self.rowcount

    def fetchone(self):
        return self._real_cur.fetchone()

    def fetchall(self):
        return self._real_cur.fetchall()

    def close(self):
        if self._real_cur is not None:
            self._real_cur.close()
            self._real_cur = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


class BufferingConnection:
    """连接代理：写入本地缓冲，读懒开真 NAS 连接透传。"""

    def __init__(self, buffer_path: str, db_config: dict):
        self._path = buffer_path
        self._db = db_config
        self._local = _open_local(buffer_path)
        self._nas_conn = None

    def _append(self, sql, params, is_many: bool) -> None:
        self._local.execute(
            "INSERT INTO pending_writes (sql, params, is_many) VALUES (?,?,?)",
            (sql, json.dumps(params, default=str), 1 if is_many else 0),
        )
        self._local.commit()

    def _get_nas(self):
        if self._nas_conn is None:
            self._nas_conn = pymysql.connect(**self._db)
            with self._nas_conn.cursor() as c:
                c.execute("SET time_zone = '+08:00'")
        return self._nas_conn

    def _nas_cursor(self, cursorclass=None):
        nas = self._get_nas()
        return nas.cursor(cursorclass) if cursorclass else nas.cursor()

    def cursor(self, cursor=None):
        return BufferingCursor(self, cursorclass=cursor)

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        if self._nas_conn is not None:
            self._nas_conn.close()
            self._nas_conn = None
        self._local.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def pending_count(buffer_path: str) -> int:
    if not os.path.exists(buffer_path):
        return 0
    conn = sqlite3.connect(buffer_path)
    try:
        return conn.execute("SELECT COUNT(*) FROM pending_writes").fetchone()[0]
    except sqlite3.OperationalError:
        return 0
    finally:
        conn.close()


def _get_nas_for_flush():
    """flush 用的真 NAS 连接（含 get_conn 的连接重试）。独立函数便于测试 mock。"""
    from db import get_conn
    return get_conn()


def flush(buffer_path: str) -> dict:
    """按 seq 顺序重放 pending_writes 到 NAS，每条成功即删（断点续传）。

    连接/重放出错则抛出（缓冲保留已删之外的行，可重跑续传）。
    返回 {"replayed": n, "remaining": m}。
    """
    if not os.path.exists(buffer_path):
        return {"replayed": 0, "remaining": 0}
    local = sqlite3.connect(buffer_path)
    try:
        rows = local.execute(
            "SELECT seq, sql, params, is_many FROM pending_writes ORDER BY seq ASC"
        ).fetchall()
        if not rows:
            return {"replayed": 0, "remaining": 0}
        nas = _get_nas_for_flush()
        replayed = 0
        try:
            for seq, sql, params_json, is_many in rows:
                params = json.loads(params_json) if params_json else None
                with nas.cursor() as cur:
                    if is_many:
                        cur.executemany(sql, params)
                    else:
                        cur.execute(sql, params)
                nas.commit()
                local.execute("DELETE FROM pending_writes WHERE seq=?", (seq,))
                local.commit()
                replayed += 1
        finally:
            nas.close()
        remaining = local.execute("SELECT COUNT(*) FROM pending_writes").fetchone()[0]
        log.info(f"flush: replayed={replayed} remaining={remaining}")
        return {"replayed": replayed, "remaining": remaining}
    finally:
        local.close()