import json
import sqlite3
import pytest


def test_get_conn_retries_on_operational_error(monkeypatch):
    """连接失败 2 次后第 3 次成功 → pymysql.connect 调 3 次，sleep 不真睡。"""
    import db
    calls = {"n": 0}

    class FakeCursor:
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def execute(self, *a): pass

    class FakeConn:
        def cursor(self): return FakeCursor()

    def fake_connect(**kw):
        calls["n"] += 1
        if calls["n"] < 3:
            raise db.pymysql.err.OperationalError(2003, "Host is down")
        return FakeConn()

    monkeypatch.setattr(db.pymysql, "connect", fake_connect)
    monkeypatch.setattr(db.time, "sleep", lambda s: None)
    monkeypatch.setattr(db, "DB_CONNECT_RETRIES", 3)
    monkeypatch.setattr(db, "DB_CONNECT_BACKOFF", 0.01)

    conn = db.get_conn()
    assert calls["n"] == 3
    assert isinstance(conn, FakeConn)