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


def test_is_write_classification():
    from futu_ingest.local_buffer import _is_write
    assert _is_write("INSERT INTO t VALUES (1)")
    assert _is_write("  update t set a=1")
    assert _is_write("REPLACE INTO t VALUES (1)")
    assert _is_write("DELETE FROM t")
    assert not _is_write("SELECT 1")
    assert not _is_write("  show tables")
    assert not _is_write("SET time_zone='+08:00'")


def test_executemany_buffers_to_local(tmp_path):
    """executemany(INSERT) → pending_writes 增 1 行，params json 往返还原。"""
    from futu_ingest.local_buffer import BufferingConnection, pending_count
    path = str(tmp_path / "buf.sqlite")
    rows = [("AAPL", "2026-06-06", 100), ("MSFT", "2026-06-06", 200)]
    conn = BufferingConnection(path, db_config={})
    with conn.cursor() as cur:
        cur.executemany("INSERT INTO us_x (ticker, date, v) VALUES (%s,%s,%s)", rows)
        assert cur.rowcount == 2
    conn.commit()  # no-op
    conn.close()

    assert pending_count(path) == 1
    raw = sqlite3.connect(path).execute(
        "SELECT sql, params, is_many FROM pending_writes").fetchone()
    assert raw[0].startswith("INSERT INTO us_x")
    assert json.loads(raw[1]) == [["AAPL", "2026-06-06", 100],
                                  ["MSFT", "2026-06-06", 200]]
    assert raw[2] == 1