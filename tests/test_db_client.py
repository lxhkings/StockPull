"""core.db_client 纯连接组件测试。"""
from unittest.mock import patch

import pytest
import pymysql


def test_get_conn_local_first_returns_buffering_connection():
    """本地优先模式开启时返回 BufferingConnection。"""
    from core.db_client import get_conn, set_local_first
    set_local_first(True)
    try:
        from core.local_buffer import BufferingConnection
        conn = get_conn()
        assert isinstance(conn, BufferingConnection)
        conn.close()
    finally:
        set_local_first(False)


def test_query_returns_list_of_dicts():
    """query 执行 SELECT 并返回 list[dict]。"""
    from core.db_client import query

    class FakeDictCursor:
        def execute(self, sql, params=None): pass
        def fetchall(self):
            return [{"ticker": "AAPL"}]
        def __enter__(self): return self
        def __exit__(self, *a): pass

    class FakeConn:
        def cursor(self, cursorclass=None):
            return FakeDictCursor()
        def close(self): pass

    with patch("core.db_client.get_conn", return_value=FakeConn()):
        rows = query("SELECT ticker FROM stocks")
    assert rows == [{"ticker": "AAPL"}]


def test_execute_runs_insert_and_returns_rowcount():
    """execute 执行 INSERT 并返回影响行数。"""
    from core.db_client import execute

    class FakeCursor:
        rowcount = 5
        def execute(self, sql, params=None): pass
        def __enter__(self): return self
        def __exit__(self, *a): pass

    class FakeConn:
        def cursor(self):
            return FakeCursor()
        def commit(self): pass
        def close(self): pass

    with patch("core.db_client.get_conn", return_value=FakeConn()):
        n = execute("INSERT INTO stocks VALUES (%s)", ("AAPL",))
    assert n == 5


def test_get_conn_retries_with_linear_backoff():
    """连接失败时线性退避重试，耗尽后抛出。"""
    import core.db_client as db

    # 重置连接池
    db._pool = None
    calls = {"n": 0}

    def fake_connect(**kw):
        calls["n"] += 1
        raise pymysql.err.OperationalError(2003, "Host is down")

    with patch.object(db.pymysql, "connect", fake_connect), \
         patch.object(db.time, "sleep", lambda s: None), \
         patch.object(db, "DB_POOL_MIN_CACHED", 0), \
         patch.object(db, "DB_CONNECT_RETRIES", 2):
        with pytest.raises(pymysql.err.OperationalError):
            db.get_conn()

    assert calls["n"] == 2  # 重试 2 次（DB_CONNECT_RETRIES=2）
