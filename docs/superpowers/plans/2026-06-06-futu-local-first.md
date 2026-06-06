# Futu 本地优先采集 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Futu 抓取写本地 SQLite，再由独立 flush 阶段幂等重放到 NAS，使多小时 `futu-full`/`futu-sync` 跑期间 NAS 抖动/宕机不再毁掉整轮。

**Architecture:** 单接缝 `db.get_conn()`：本地优先模式下返回 `BufferingConnection`（鸭子类型兼容 pymysql）——写(INSERT/UPDATE)入本地 `pending_writes`，读(SELECT/SHOW/SET)透传真 NAS。`flush()` 按 seq 顺序重放、每条成功即删（断点续传）。11 个采集模块零改。

**Tech Stack:** Python 3.12, pymysql, sqlite3(标准库), pytest, uv。

参考 spec：`docs/superpowers/specs/2026-06-06-futu-local-first-design.md`

---

## File Structure

| 文件 | 责任 |
|------|------|
| `futu_ingest/local_buffer.py` | 新增。`BufferingConnection`/`BufferingCursor`（写→本地、读→NAS 透传）、`flush()`、`pending_count()` |
| `db.py` | 加 `_local_first` 标志 + `set_local_first()`；`get_conn()` 加本地优先分支 + 连接重试 |
| `config.py` | 加 `FUTU_BUFFER_PATH`（`DB_CONNECT_RETRIES/BACKOFF` 已存在） |
| `main.py` | `cmd_futu_full/sync` 包两阶段（fetch→本地、自动 flush）；新增 `futu-flush` 子命令 |
| `tests/test_futu_local_buffer.py` | 新增。缓冲分类/往返、flush 重放/断点续传、get_conn 切换/重试 |

分支：`feat/futu-local-first`（已存在，spec 已提交于此）。

---

## Task 1: config 加 FUTU_BUFFER_PATH

**Files:**
- Modify: `config.py`（在 `DB_CONNECT_BACKOFF` 行后）

- [ ] **Step 1: 加常量**

在 `config.py` 中 `DB_CONNECT_BACKOFF = ...` 那行之后追加：

```python
# Futu 本地优先缓冲文件（抓取先落本地，再 flush 到 NAS）
FUTU_BUFFER_PATH = os.getenv("FUTU_BUFFER_PATH", ".futu_buffer/pending.sqlite")
```

- [ ] **Step 2: 冒烟验证导入**

Run: `uv run python -c "import config; print(config.FUTU_BUFFER_PATH)"`
Expected: 打印 `.futu_buffer/pending.sqlite`

- [ ] **Step 3: Commit**

```bash
git add config.py
git commit -m "feat(futu): add FUTU_BUFFER_PATH config"
```

---

## Task 2: get_conn 连接重试（接线 dead config）

**Files:**
- Modify: `db.py:6-11`（imports）、`db.py:20-25`（get_conn）
- Test: `tests/test_futu_local_buffer.py`

- [ ] **Step 1: 写失败测试**

新建 `tests/test_futu_local_buffer.py`：

```python
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
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/test_futu_local_buffer.py::test_get_conn_retries_on_operational_error -v`
Expected: FAIL（`db` 无 `time` 属性 / get_conn 不重试，AttributeError 或只调 1 次）

- [ ] **Step 3: 改 db.py imports + get_conn**

`db.py` 顶部 import 区，把：

```python
import pymysql
import pymysql.cursors
import logging
from datetime import date
from typing import Optional, List, Dict
from config import DB
```

改为：

```python
import time
import pymysql
import pymysql.cursors
import logging
from datetime import date
from typing import Optional, List, Dict
from config import DB, DB_CONNECT_RETRIES, DB_CONNECT_BACKOFF
```

把 `get_conn`（现 20-25 行）整体替换为：

```python
def get_conn() -> pymysql.Connection:
    """获取数据库连接（设置 +08:00 时区）。连不上时线性退避重试。"""
    last = None
    for attempt in range(1, DB_CONNECT_RETRIES + 1):
        try:
            conn = pymysql.connect(**DB)
            with conn.cursor() as cur:
                cur.execute("SET time_zone = '+08:00'")
            return conn
        except pymysql.err.OperationalError as e:
            last = e
            if attempt < DB_CONNECT_RETRIES:
                log.warning(f"DB connect failed ({attempt}/{DB_CONNECT_RETRIES}): {e}; "
                            f"retry in {DB_CONNECT_BACKOFF * attempt}s")
                time.sleep(DB_CONNECT_BACKOFF * attempt)
    raise last
```

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/test_futu_local_buffer.py::test_get_conn_retries_on_operational_error -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add db.py tests/test_futu_local_buffer.py
git commit -m "feat(db): retry get_conn on connection failure"
```

---

## Task 3: local_buffer 写缓冲（BufferingCursor 分类 + 落本地）

**Files:**
- Create: `futu_ingest/local_buffer.py`
- Test: `tests/test_futu_local_buffer.py`

- [ ] **Step 1: 写失败测试**

在 `tests/test_futu_local_buffer.py` 追加：

```python
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
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/test_futu_local_buffer.py -k "is_write or executemany_buffers" -v`
Expected: FAIL（`No module named futu_ingest.local_buffer`）

- [ ] **Step 3: 创建 local_buffer.py（写侧）**

Create `futu_ingest/local_buffer.py`：

```python
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
```

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/test_futu_local_buffer.py -k "is_write or executemany_buffers" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add futu_ingest/local_buffer.py tests/test_futu_local_buffer.py
git commit -m "feat(futu): BufferingConnection writes to local sqlite"
```

---

## Task 4: SELECT 透传 NAS（读路径）

**Files:**
- Modify: `futu_ingest/local_buffer.py`（已在 Task 3 含透传逻辑——本任务补测试验证）
- Test: `tests/test_futu_local_buffer.py`

- [ ] **Step 1: 写失败测试**

追加：

```python
def test_select_passes_through_to_nas(tmp_path, monkeypatch):
    """SELECT 不进缓冲，转发到真 NAS 连接（mock）。"""
    from futu_ingest import local_buffer

    executed = []

    class FakeRealCursor:
        rowcount = 1
        def execute(self, sql, params=None): executed.append((sql, params))
        def fetchall(self): return [("AAPL",)]
        def close(self): pass

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

    assert executed == [("SELECT ticker FROM stocks", None)]
    assert local_buffer.pending_count(path) == 0   # SELECT 未入缓冲
```

- [ ] **Step 2: 跑测试确认通过**

（透传逻辑已在 Task 3 实现，此为回归验证。若失败说明 Task 3 透传有 bug。）

Run: `uv run pytest tests/test_futu_local_buffer.py::test_select_passes_through_to_nas -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_futu_local_buffer.py
git commit -m "test(futu): verify SELECT passthrough to NAS"
```

---

## Task 5: flush 重放（含断点续传）

**Files:**
- Modify: `futu_ingest/local_buffer.py`（加 `flush()`）
- Test: `tests/test_futu_local_buffer.py`

- [ ] **Step 1: 写失败测试**

追加（含一个共享 fake NAS 工具）：

```python
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
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/test_futu_local_buffer.py -k flush -v`
Expected: FAIL（`local_buffer` 无 `flush` / `_get_nas_for_flush`）

- [ ] **Step 3: 加 flush + _get_nas_for_flush**

在 `futu_ingest/local_buffer.py` 末尾追加：

```python
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
```

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/test_futu_local_buffer.py -k flush -v`
Expected: PASS（3 个 flush 测试）

- [ ] **Step 5: Commit**

```bash
git add futu_ingest/local_buffer.py tests/test_futu_local_buffer.py
git commit -m "feat(futu): flush replays local buffer to NAS, resumable"
```

---

## Task 6: db 本地优先开关（set_local_first + get_conn 分支）

**Files:**
- Modify: `db.py`（加 `_local_first` + `set_local_first`；`get_conn` 顶部分支）
- Test: `tests/test_futu_local_buffer.py`

- [ ] **Step 1: 写失败测试**

追加：

```python
def test_set_local_first_toggles_get_conn(monkeypatch, tmp_path):
    import db
    from futu_ingest.local_buffer import BufferingConnection
    monkeypatch.setattr(db, "FUTU_BUFFER_PATH", str(tmp_path / "buf.sqlite"))

    db.set_local_first(True)
    try:
        conn = db.get_conn()
        assert isinstance(conn, BufferingConnection)
        conn.close()
    finally:
        db.set_local_first(False)

    # 关闭后走真连接路径（mock pymysql 验证不再返回 Buffering）
    monkeypatch.setattr(db.pymysql, "connect", lambda **kw: (_ for _ in ()).throw(
        db.pymysql.err.OperationalError(2003, "Host is down")))
    monkeypatch.setattr(db, "DB_CONNECT_RETRIES", 1)
    with pytest.raises(db.pymysql.err.OperationalError):
        db.get_conn()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/test_futu_local_buffer.py::test_set_local_first_toggles_get_conn -v`
Expected: FAIL（`db` 无 `set_local_first` / `FUTU_BUFFER_PATH`）

- [ ] **Step 3: 改 db.py**

`db.py` import 区把：

```python
from config import DB, DB_CONNECT_RETRIES, DB_CONNECT_BACKOFF
```

改为：

```python
from config import DB, DB_CONNECT_RETRIES, DB_CONNECT_BACKOFF, FUTU_BUFFER_PATH
```

在 import 区之后、`get_conn` 之前加：

```python
_local_first = False   # 进程内全局标志（跨线程可见；futu CLI 调用整进程只做 futu）


def set_local_first(on: bool) -> None:
    """开/关本地优先模式。开启后 get_conn 返回 BufferingConnection（写入本地缓冲）。"""
    global _local_first
    _local_first = on
```

把 `get_conn` 整体替换为（在 Task 2 基础上加最前面的本地优先分支）：

```python
def get_conn() -> pymysql.Connection:
    """获取数据库连接（设置 +08:00 时区）。连不上时线性退避重试。

    本地优先模式下返回 BufferingConnection：写入本地缓冲，读透传 NAS。
    """
    if _local_first:
        from futu_ingest.local_buffer import BufferingConnection
        return BufferingConnection(FUTU_BUFFER_PATH, DB)
    last = None
    for attempt in range(1, DB_CONNECT_RETRIES + 1):
        try:
            conn = pymysql.connect(**DB)
            with conn.cursor() as cur:
                cur.execute("SET time_zone = '+08:00'")
            return conn
        except pymysql.err.OperationalError as e:
            last = e
            if attempt < DB_CONNECT_RETRIES:
                log.warning(f"DB connect failed ({attempt}/{DB_CONNECT_RETRIES}): {e}; "
                            f"retry in {DB_CONNECT_BACKOFF * attempt}s")
                time.sleep(DB_CONNECT_BACKOFF * attempt)
    raise last
```

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/test_futu_local_buffer.py::test_set_local_first_toggles_get_conn -v`
Expected: PASS

- [ ] **Step 5: 全量回归**

Run: `uv run pytest tests/test_futu_local_buffer.py -v`
Expected: 全 PASS

- [ ] **Step 6: Commit**

```bash
git add db.py tests/test_futu_local_buffer.py
git commit -m "feat(db): add local-first toggle to get_conn"
```

---

## Task 7: main.py 两阶段 + futu-flush 子命令

**Files:**
- Modify: `main.py`（`cmd_futu_full`/`cmd_futu_sync` 现 201-210 行；`_build_parser` futu 区 79-82 行；`main()` 派发 239-242 行）

- [ ] **Step 1: 改 cmd_futu_full / cmd_futu_sync 为两阶段**

把 `main.py` 现有：

```python
def cmd_futu_full(scope: str) -> int:
    from futu_ingest.orchestrator import run_sync
    print(run_sync(scope=scope, force=True))
    return 0


def cmd_futu_sync(scope: str) -> int:
    from futu_ingest.orchestrator import run_sync
    print(run_sync(scope=scope, force=False))
    return 0
```

替换为：

```python
def _run_futu(scope: str, force: bool) -> int:
    """两阶段：fetch 写本地缓冲 → 自动 flush 到 NAS。flush 失败则保留缓冲、提示兜底。"""
    import db
    from futu_ingest.orchestrator import run_sync
    from futu_ingest.local_buffer import flush, pending_count
    from config import FUTU_BUFFER_PATH

    db.set_local_first(True)
    try:
        rep = run_sync(scope=scope, force=force)
    finally:
        db.set_local_first(False)
    print(rep)

    try:
        fstat = flush(FUTU_BUFFER_PATH)
        print(f"flush -> NAS: {fstat}")
    except Exception as e:  # noqa: BLE001
        n = pending_count(FUTU_BUFFER_PATH)
        print(f"FETCH 完成并已存本地。FLUSH 失败: {e}\n"
              f"缓冲 {n} 条待传保留。NAS 恢复后跑: uv run main.py futu-flush")
        return 1
    return 0


def cmd_futu_full(scope: str) -> int:
    return _run_futu(scope, force=True)


def cmd_futu_sync(scope: str) -> int:
    return _run_futu(scope, force=False)


def cmd_futu_flush() -> int:
    from futu_ingest.local_buffer import flush, pending_count
    from config import FUTU_BUFFER_PATH
    n = pending_count(FUTU_BUFFER_PATH)
    if n == 0:
        print("无待传数据。")
        return 0
    print(f"待传 {n} 条，开始 flush -> NAS ...")
    print(flush(FUTU_BUFFER_PATH))
    return 0
```

- [ ] **Step 2: 注册 futu-flush 子命令**

`main.py` `_build_parser` 中 futu-sync 注册（现 81-82 行）之后追加：

```python
    sub.add_parser("futu-flush", help="把本地缓冲重放到 NAS（futu-full/sync flush 失败后兜底）")
```

- [ ] **Step 3: main() 派发加分支**

`main.py` `main()` 中 `futu-sync` 分支（现 241-242 行）之后追加：

```python
    if args.cmd == "futu-flush":
        return cmd_futu_flush()
```

- [ ] **Step 4: 冒烟验证 CLI 解析**

Run: `uv run python -c "import main; main.main(['futu-flush'])"`
Expected: 打印 `无待传数据。`（无缓冲文件时），退出 0，无报错

- [ ] **Step 5: 验证 help 列出 futu-flush**

Run: `uv run main.py --help 2>&1 | grep futu-flush`
Expected: 显示 `futu-flush` 一行

- [ ] **Step 6: Commit**

```bash
git add main.py
git commit -m "feat(futu): two-phase futu-full/sync + futu-flush command"
```

---

## Task 8: 文档更新 + 全量回归

**Files:**
- Modify: `CLAUDE.md`（Futu 命令区）、`README.md`（若有 Futu 流程说明）

- [ ] **Step 1: CLAUDE.md 加 futu-flush 说明**

`CLAUDE.md` 的 `# Futu 美股基本面` 命令块，在 `futu-sync` 行后追加：

```bash
uv run main.py futu-flush           # 兜底：把本地缓冲重放到 NAS（futu-full/sync flush 失败后）
```

并在该块下补一句说明：

```
# futu-full/futu-sync 先写本地缓冲（.futu_buffer/pending.sqlite），收尾自动 flush 到 NAS。
# NAS 中途宕机不丢数据；flush 失败时跑 futu-flush 兜底。
```

- [ ] **Step 2: 全量测试回归**

Run: `uv run pytest tests/ -q`
Expected: 全 PASS（无回归）

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(futu): document local-first flow and futu-flush"
```

---

## Self-Review notes

- **Spec 覆盖**：BufferingConnection/Cursor(Task3,4)、flush 断点续传(Task5)、set_local_first+get_conn 分支(Task6)、连接重试(Task2)、FUTU_BUFFER_PATH(Task1)、main 两阶段+futu-flush(Task7)、PIT 顺序重放（Task5 `test_flush_replays_in_order` 验证）、文档(Task8)。`.gitignore` `.futu_buffer/` 已于 spec 提交时加入。
- **类型一致**：`BufferingConnection(buffer_path, db_config)`、`flush(buffer_path)->dict{replayed,remaining}`、`pending_count(buffer_path)->int`、`set_local_first(on)`、`_get_nas_for_flush()` 全程一致。
- **created_at 漂移**、**NAS 开头不可达**、**跨轮节流需先 flush** 见 spec，属可接受/操作约定，无需代码任务。
