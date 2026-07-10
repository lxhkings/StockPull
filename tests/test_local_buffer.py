import json
import sqlite3
import threading
import pytest


def test_get_conn_retries_on_operational_error(monkeypatch):
    """连接失败 2 次后第 3 次成功 → pymysql.connect 调 3 次，sleep 不真睡。"""
    import core.db_client as db
    # 重置连接池（避免前次测试缓存影响）
    monkeypatch.setattr(db, "_pool", None)
    calls = {"n": 0}

    class FakeCursor:
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def execute(self, *a): pass
        def close(self): pass

    class FakeConn:
        def cursor(self): return FakeCursor()
        def close(self): pass

    def fake_connect(**kw):
        calls["n"] += 1
        if calls["n"] < 3:
            raise db.pymysql.err.OperationalError(2003, "Host is down")
        return FakeConn()

    monkeypatch.setattr(db.pymysql, "connect", fake_connect)
    monkeypatch.setattr(db.time, "sleep", lambda s: None)
    monkeypatch.setattr(db, "DB_POOL_MIN_CACHED", 0)
    monkeypatch.setattr(db, "DB_CONNECT_RETRIES", 3)
    monkeypatch.setattr(db, "DB_CONNECT_BACKOFF", 0.01)

    conn = db.get_conn()
    assert calls["n"] == 3
    # 连接池包装后返回 PooledDedicatedDBConnection，底层是 FakeConn
    assert isinstance(conn._con._con, FakeConn)


def test_is_write_classification():
    from core.local_buffer import _is_write
    assert _is_write("INSERT INTO t VALUES (1)")
    assert _is_write("  update t set a=1")
    assert _is_write("REPLACE INTO t VALUES (1)")
    assert _is_write("DELETE FROM t")
    assert not _is_write("SELECT 1")
    assert not _is_write("  show tables")
    assert not _is_write("SET time_zone='+08:00'")


def test_executemany_buffers_to_local(tmp_path):
    """executemany(INSERT) → pending_writes 增 1 行，params json 往返还原。"""
    from core.local_buffer import BufferingConnection, pending_count
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
    from core import local_buffer

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
    from core.local_buffer import _SCHEMA
    c = sqlite3.connect(path)
    c.execute(_SCHEMA)
    for sql, params, many in items:
        c.execute("INSERT INTO pending_writes (sql, params, is_many) VALUES (?,?,?)",
                  (sql, json.dumps(params, default=str), many))
    c.commit(); c.close()


def test_flush_replays_in_order_and_clears(tmp_path, monkeypatch):
    from core import local_buffer
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
    from core import local_buffer
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
    from core import local_buffer
    assert local_buffer.flush(str(tmp_path / "nope.sqlite")) == {"replayed": 0, "remaining": 0}


class _FakeNasConnThreadSafe:
    """线程安全版假 NAS：每个 worker 独立实例，用共享 list+lock 汇总记录。"""
    def __init__(self, shared_executed, lock, fail_on=None):
        self._shared = shared_executed
        self._lock = lock
        self._fail_on = fail_on or set()

    def cursor(self, cursorclass=None):
        outer = self

        class Cur:
            def __enter__(self): return self
            def __exit__(self, *a): pass
            def execute(self, sql, params=None):
                if params in outer._fail_on:
                    raise __import__("pymysql").err.OperationalError(2006, "gone away")
                with outer._lock:
                    outer._shared.append(("execute", sql, params))
            def executemany(self, sql, params=None):
                key = json.dumps(params, default=str)
                if key in outer._fail_on:
                    raise __import__("pymysql").err.OperationalError(2006, "gone away")
                with outer._lock:
                    outer._shared.append(("executemany", sql, params))
            def close(self): pass
        return Cur()

    def commit(self): pass
    def close(self): pass


def test_flush_parallel_clears_all_disjoint_batches(tmp_path, monkeypatch):
    """N 条同表独立 upsert，workers=3 并发跑完，全部清空、全部重放。"""
    from core import local_buffer
    path = str(tmp_path / "buf.sqlite")
    _seed(path, [
        (f"INSERT INTO cn_valuation_snapshot VALUES (%s)", [[f"row{i}"]], 1)
        for i in range(9)
    ])
    executed = []
    lock = threading.Lock()
    monkeypatch.setattr(
        local_buffer, "_get_nas_for_flush",
        lambda: _FakeNasConnThreadSafe(executed, lock),
    )

    res = local_buffer.flush_parallel(path, workers=3)

    assert res == {"replayed": 9, "remaining": 0}
    assert len(executed) == 9
    assert local_buffer.pending_count(path) == 0


def test_flush_parallel_resumable_on_partial_failure(tmp_path, monkeypatch):
    """某个 worker 的某一批失败 → 该批及同 worker 之后的批留在缓冲，其它 worker 成功的批已清除。"""
    from core import local_buffer
    path = str(tmp_path / "buf.sqlite")
    _seed(path, [
        ("INSERT INTO t VALUES (%s)", [["a"]], 1),
        ("INSERT INTO t VALUES (%s)", [["b"]], 1),
        ("INSERT INTO t VALUES (%s)", [["FAIL"]], 1),
        ("INSERT INTO t VALUES (%s)", [["d"]], 1),
    ])
    executed = []
    lock = threading.Lock()
    fail_on = {json.dumps([["FAIL"]])}
    monkeypatch.setattr(
        local_buffer, "_get_nas_for_flush",
        lambda: _FakeNasConnThreadSafe(executed, lock, fail_on=fail_on),
    )

    with pytest.raises(local_buffer.pymysql.err.OperationalError):
        local_buffer.flush_parallel(path, workers=2)

    # 失败批和同 worker 之后没跑到的批仍在缓冲里，其它 worker 已成功的批被清除
    assert local_buffer.pending_count(path) < 4
    assert local_buffer.pending_count(path) >= 1


def test_flush_parallel_no_file(tmp_path):
    from core import local_buffer
    assert local_buffer.flush_parallel(str(tmp_path / "nope.sqlite")) == {"replayed": 0, "remaining": 0}


def test_flush_parallel_no_pending(tmp_path):
    from core import local_buffer
    from core.local_buffer import _SCHEMA
    path = str(tmp_path / "buf.sqlite")
    c = sqlite3.connect(path)
    c.execute(_SCHEMA)
    c.commit(); c.close()
    assert local_buffer.flush_parallel(path) == {"replayed": 0, "remaining": 0}


def test_set_local_first_toggles_get_conn(monkeypatch, tmp_path):
    import core.db_client as db
    from core.local_buffer import BufferingConnection
    monkeypatch.setattr(db, "FUTU_BUFFER_PATH", str(tmp_path / "buf.sqlite"))

    db.set_local_first(True)
    try:
        conn = db.get_conn()
        assert isinstance(conn, BufferingConnection)
        conn.close()
    finally:
        db.set_local_first(False)

    # 关闭后走真连接路径（mock pymysql 验证不再返回 Buffering）
    monkeypatch.setattr(db, "_pool", None)  # 重置连接池
    monkeypatch.setattr(db.pymysql, "connect", lambda **kw: (_ for _ in ()).throw(
        db.pymysql.err.OperationalError(2003, "Host is down")))
    monkeypatch.setattr(db, "DB_CONNECT_RETRIES", 1)
    with pytest.raises(db.pymysql.err.OperationalError):
        db.get_conn()