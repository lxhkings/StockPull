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


def test_select_passes_through_to_nas(tmp_path, monkeypatch):
    """SELECT 不进缓冲，转发到真 NAS 连接（mock）。"""
    from futu_ingest import local_buffer

    executed = []

    class FakeRealCursor:
        rowcount = 1
        def execute(self, sql, params=None): executed.append((sql, params))
        def fetchall(self): return [("AAPL",)]
        def close(self): pass
        def __enter__(self): return self
        def __exit__(self, *a): pass

    class FakeNas:
        def cursor(self, cursorclass=None): return FakeRealCursor()
        def close(self): pass

    monkeypatch.setattr(local_buffer.pymysql, "connect", lambda **kw: FakeNas())

    path = str(tmp_path / "buf.sqlite")
    conn = local_buffer.BufferingConnection(path, db_config={})
    with conn.cursor() as cur:
        cur.execute("SELECT ticker FROM stocks")
        assert cur.fetchall() == [("AAPL",)]
    conn.close()

    # SELECT 和 SET time_zone 都应透传到 NAS；SELECT 不入缓冲
    assert ("SELECT ticker FROM stocks", None) in executed
    assert local_buffer.pending_count(path) == 0


class _FakeNasConn:
    """记录重放语句的假 NAS。fail_at=N 时第 N 条 execute 抛连接错。"""
    def __init__(self, fail_at=None):
        self.executed = []
        self.committed = 0
        self._fail_at = fail_at
        self._n = 0

    def cursor(self, cursorclass=None):
        outer = self

        class Cur:
            def __enter__(self): return self
            def __exit__(self, *a): pass
            def execute(self, sql, params=None):
                outer._n += 1
                if outer._fail_at and outer._n == outer._fail_at:
                    raise __import__("pymysql").err.OperationalError(2006, "gone away")
                outer.executed.append(("execute", sql, params))
            def executemany(self, sql, params=None):
                outer._n += 1
                if outer._fail_at and outer._n == outer._fail_at:
                    raise __import__("pymysql").err.OperationalError(2006, "gone away")
                outer.executed.append(("executemany", sql, params))
            def close(self): pass
        return Cur()

    def commit(self): self.committed += 1
    def close(self): pass


def _seed(path, items):
    """items: list[(sql, params, is_many)]。"""
    import sqlite3
    from futu_ingest.local_buffer import _SCHEMA
    c = sqlite3.connect(path)
    c.execute(_SCHEMA)
    for sql, params, many in items:
        c.execute("INSERT INTO pending_writes (sql, params, is_many) VALUES (?,?,?)",
                  (sql, json.dumps(params, default=str), many))
    c.commit(); c.close()


def test_flush_replays_in_order_and_clears(tmp_path, monkeypatch):
    from futu_ingest import local_buffer
    path = str(tmp_path / "buf.sqlite")
    _seed(path, [
        ("INSERT INTO us_fin_income VALUES (%s)", [["A"]], 1),
        ("INSERT INTO us_earnings_dates VALUES (%s)", [["A"]], 1),
        ("UPDATE us_fin_income f JOIN us_earnings_dates e SET f.ann=e.pub", None, 0),
    ])
    fake = _FakeNasConn()
    monkeypatch.setattr(local_buffer, "_get_nas_for_flush", lambda: fake)

    res = local_buffer.flush(path)

    assert res == {"replayed": 3, "remaining": 0}
    ops = [k for k, s, _ in fake.executed]
    assert ops == ["executemany", "executemany", "execute"]   # PIT(UPDATE) 在两 INSERT 后
    tables = [s.split()[2] for k, s, _ in fake.executed[:2]]   # INSERT INTO <表>
    assert tables == ["us_fin_income", "us_earnings_dates"]
    assert local_buffer.pending_count(path) == 0


def test_flush_resumable_on_nas_error(tmp_path, monkeypatch):
    from futu_ingest import local_buffer
    path = str(tmp_path / "buf.sqlite")
    _seed(path, [
        ("INSERT INTO a VALUES (%s)", [["x"]], 1),
        ("INSERT INTO b VALUES (%s)", [["y"]], 1),
        ("INSERT INTO c VALUES (%s)", [["z"]], 1),
    ])
    fake = _FakeNasConn(fail_at=2)
    monkeypatch.setattr(local_buffer, "_get_nas_for_flush", lambda: fake)

    with pytest.raises(local_buffer.pymysql.err.OperationalError):
        local_buffer.flush(path)

    # 第 1 条已删，第 2/3 条保留
    assert local_buffer.pending_count(path) == 2

    # NAS 恢复后二次 flush 清空
    fake2 = _FakeNasConn()
    monkeypatch.setattr(local_buffer, "_get_nas_for_flush", lambda: fake2)
    res = local_buffer.flush(path)
    assert res == {"replayed": 2, "remaining": 0}
    assert local_buffer.pending_count(path) == 0


def test_flush_no_file(tmp_path):
    from futu_ingest import local_buffer
    assert local_buffer.flush(str(tmp_path / "nope.sqlite")) == {"replayed": 0, "remaining": 0}