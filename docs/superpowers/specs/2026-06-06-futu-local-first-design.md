# Futu 本地优先采集 (local-first ingest)

**日期:** 2026-06-06
**状态:** 设计已批准，待实现

## 问题

`futu-full` / `futu-sync` 跑几小时（受 API 限频）。期间所有 11 个采集模块直写
NAS（`192.168.8.9` MariaDB）。NAS 中途连接抖动/宕机 → `executemany` 抛
`(2006, "MySQL server has gone away")`，错误处理路径再次 `get_conn()` 又抛
`(2003, "Host is down")` → 整轮崩溃，几小时抓取作废。

根因：抓取与落库强耦合，每票实时写 NAS，NAS 任何抖动都能毁掉整轮。

## 目标

抓取与落库解耦，两阶段：

1. **FETCH** — 抓取写本地 SQLite，全程不依赖 NAS 写连接。NAS 中途挂也不崩。
2. **FLUSH** — 把本地缓冲重放到 NAS，幂等、可断点续传。

非目标：完全离线采集（票池/节流读仍需 NAS 在开头可达）。本设计针对**韧性**——
NAS 开头可达、中途可能抖动的场景。

## 关键观察（现有代码）

- 所有 11 模块落库形状一致：`fetch → build rows → with get_conn() as conn:
  cur.executemany(<表专属 INSERT...ON DUPLICATE KEY UPDATE>, rows); conn.commit()`。
- 单一接缝 `get_conn()`（`db.py`）——所有写都过它。
- upsert 幂等（`ON DUPLICATE KEY UPDATE`）→ 重放安全，重复重放无害。
- futu 流程读 NAS 只在**开头**且**快**：
  - `list_us_tickers()`（orchestrator，取票池，1 次）
  - `fresh_tickers()`（sync.py，节流判断，每 data_type 1 次，在该 type 写之前）
- 写则全程：数据 `executemany` + `mark_ok/mark_error/mark_skip` 写 `sync_log`。
- 价格 pipeline（`market_us/cn/hk`）也用 `get_conn()`——本设计**不得**影响它们。

## 架构

```
futu-full / futu-sync
   │
   ├─ phase 1: FETCH
   │   db.set_local_first(True)
   │   run_sync(scope, force)
   │     读(票池/节流): SELECT/SHOW/SET  → 透传真 NAS 读连接(懒开)
   │     写(数据/sync_log): INSERT/UPDATE → 追加本地 SQLite
   │   db.set_local_first(False)
   │        │
   │        ▼  .futu_buffer/pending.sqlite
   │        pending_writes(seq, sql, params_json, is_many, ts)
   │
   └─ phase 2: FLUSH (自动收尾)
       flush(buffer_path)
         按 seq 升序重放 → NAS，每条成功即删（断点续传）
       成功: 缓冲清空
       失败(NAS 挂): 缓冲保留，提示手动 `uv run main.py futu-flush`
```

## 组件

### 新模块 `futu_ingest/local_buffer.py`

模块化核心。鸭子类型兼容 pymysql 的连接/游标接口，模块代码零改。

**`BufferingConnection`**
- 构造：`BufferingConnection(buffer_path)`。不开 NAS 写连接。
- `cursor(cursor=None)` → 返回 `BufferingCursor`（支持 `pymysql.cursors.DictCursor`
  传入，用于 SELECT 透传）。
- `commit()` / `rollback()` → no-op（写已落本地 SQLite，append 自身 autocommit）。
- `close()` → 关闭懒开的 NAS 读连接（若有）+ 本地 SQLite 连接。
- `__enter__` 返回 self；`__exit__` 调 `close()`（对齐 `with get_conn() as conn:` 用法）。
- 懒持有一个真 NAS 读连接（首次遇 SELECT 时 `pymysql.connect(**DB)` 并
  `SET time_zone='+08:00'`）。

**`BufferingCursor`**
- 按 SQL 首个关键字（去前导空白/注释后大写比较）分类：
  - `INSERT` / `REPLACE` / `UPDATE` / `DELETE` → 写本地：
    - `execute(sql, params)`：append 一行 `(sql, json(params), is_many=0)`；
      `rowcount = len(params 行数 or 1)`（best-effort，调用方一般不依赖 INSERT rowcount）。
    - `executemany(sql, seq_of_params)`：append `(sql, json(list), is_many=1)`；
      `rowcount = len(seq)`。
  - `SELECT` / `SHOW` / `SET` / 其它 → 透传：转发到懒开 NAS 读连接的真游标，
    `fetchone/fetchall/rowcount` 代理之。
- `__enter__/__exit__` 对齐 `with conn.cursor() as cur:`。

**params 序列化**：`json.dumps(params, default=str)`。日期/Decimal → 字符串，
MySQL 绑定接受；None → null → None。重放时 `json.loads` 还原为 list，pymysql
正常绑定。（已有上游把 NaN 转 None，无特殊浮点。）

**本地 schema**（SQLite，`pending_writes`）：
```sql
CREATE TABLE IF NOT EXISTS pending_writes (
    seq        INTEGER PRIMARY KEY AUTOINCREMENT,
    sql        TEXT    NOT NULL,
    params     TEXT,                -- json
    is_many    INTEGER NOT NULL,    -- 0=execute 1=executemany
    ts         TEXT    DEFAULT (datetime('now'))
);
```

**`flush(buffer_path) -> dict`**
- 无缓冲文件或空表 → 返回 `{"replayed": 0, "remaining": 0}`，不报错。
- 开 NAS 连接（`db.get_conn()`，吃到 `DB_CONNECT_RETRIES/BACKOFF` 连接重试）。
- 按 `seq ASC` 取，逐条 `execute`/`executemany` 重放，**每条成功后**
  `DELETE FROM pending_writes WHERE seq=?` 并 commit NAS + commit 本地。
  → 断点续传：中途 NAS 挂，已重放的已删，重跑从剩余继续。
- 某条重放失败（非连接类错误，如脏数据）：记 log，保留该行，继续后续？
  → **不跳过**：连接类错误（gone away/host is down）直接抛出中止（缓冲保留待重试）；
  非连接类错误同样中止并打印失败 `seq`+`sql`，避免静默丢数据。
- 返回 `{"replayed": n, "remaining": pending_count()}`。

**`pending_count(buffer_path) -> int`** — 读 `pending_writes` 行数（文件不存在返回 0）。

### `db.py` 改动（最小）

```python
_local_first = False   # 模块级标志，进程内全局（跨线程可见）

def set_local_first(on: bool, buffer_path: str | None = None) -> None:
    global _local_first
    _local_first = on

def get_conn():
    if _local_first:
        from futu_ingest.local_buffer import BufferingConnection
        return BufferingConnection(FUTU_BUFFER_PATH)
    # 连接重试（本次新增）：连不上时线性退避重试
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
                time.sleep(DB_CONNECT_BACKOFF * attempt)
    raise last
```

connect-retry 让 flush 阶段更稳（NAS 重启 1-2 分钟内续命）。`DB_CONNECT_RETRIES`
/ `DB_CONNECT_BACKOFF` 常量上一轮已加进 config.py（当时未接线，本次接入 get_conn）。

- 全局标志（非 contextvar）：futu 用 `ThreadPoolExecutor`/多 worker 线程，
  contextvar 不自动传播到线程池；全局标志跨线程可见。该 CLI 调用整进程只做
  futu，无与价格 pipeline 的并发冲突。
- 延迟 import 避免循环依赖（`local_buffer` import `db`）。

### `main.py` 改动

- `cmd_futu_full(scope)` / `cmd_futu_sync(scope)`：
  ```
  db.set_local_first(True)
  try:
      rep = run_sync(scope=scope, force=...)
  finally:
      db.set_local_first(False)
  # 自动收尾 flush
  try:
      fstat = flush(FUTU_BUFFER_PATH)
      print(rep, fstat)
  except Exception as e:
      print(f"FETCH 完成并存本地。FLUSH 失败({e})。"
            f"缓冲 {pending_count()} 条保留，NAS 恢复后跑: uv run main.py futu-flush")
  ```
- 新增子命令 `futu-flush` → `cmd_futu_flush()`：`print(flush(FUTU_BUFFER_PATH))`。
  无缓冲则提示 "无待传数据"。

### `config.py`

```python
FUTU_BUFFER_PATH = os.getenv("FUTU_BUFFER_PATH", ".futu_buffer/pending.sqlite")
```
`DB_CONNECT_RETRIES` / `DB_CONNECT_BACKOFF` 上一轮已加（本次在 get_conn 接线使用）。

### `.gitignore`

追加 `.futu_buffer/`。

## 数据流细节与不变量

### 语句顺序 = 正确性关键
重放严格按 `seq`（= 抓取时写入顺序）。这保证跨表依赖正确：

- **PIT 回填**（`run_pit_backfill` 的 `UPDATE us_fin_* JOIN us_earnings_dates`）：
  orchestrator 中 `financial`(先) → `earnings`+PIT(后)。缓冲序为
  `fin INSERT... → earnings INSERT... → PIT UPDATE...`。按 seq 重放 → fin 行入库
  → earnings 行入库 → PIT JOIN 命中。**PIT 无需特殊处理**，当作普通缓冲 UPDATE
  语句即可（这是相对原 A+B+C 方案的简化）。
- scope=earnings 单跑（无 financial）时，PIT 的 JOIN 更新 NAS 上已有 fin 表
  （往轮已落），用新 flush 的 earnings → flush 时对 NAS 执行，命中。

### sync_log 节流
- `mark_ok/error/skip` 写 `sync_log` 也被缓冲。
- `fresh_tickers()` 在每个 `ticker_stream` 开头读 `sync_log`（透传真 NAS）。
  同一轮内：fresh 在该 data_type 写之前算好一次，跨 data_type 不重叠 → 缓冲
  sync_log 不破坏本轮节流。
- 跨轮：sync_log 须 flush 到 NAS 后下轮节流才准。自动收尾 flush 保证。
- **操作约定**：若某轮 fetch 完但 flush 失败（NAS 挂），下次跑 futu-sync 前应先
  `futu-flush`。否则下轮 `fresh_tickers` 读到旧 NAS 状态会重抓（API 浪费，但数据
  幂等无害）。

### created_at 漂移（已接受）
`*_daily` 等表的 `created_at DEFAULT CURRENT_TIMESTAMP` 在 INSERT 执行时取值
= flush 时刻，非 fetch 时刻。逻辑日期字段（`snapshot_date` / `date` / `period_end`）
在 values 内已正确。created_at 偏移分钟~小时级，可接受。

### NAS 开头不可达
若 fetch 启动时 NAS 就连不上（首个 SELECT 透传失败），run 无法取票池 → 清晰报错
退出。符合预期（本设计针对"开头可达、中途抖动"）。

## 与上一改动（A+B+C）的关系
上一未完成改动只加了 `DB_CONNECT_RETRIES/BACKOFF` 两个 config 常量（未接线，
当前为 dead config）。本次在 `get_conn()` 接入连接重试（= 原 A），flush 吃到。
本设计下抓取阶段不碰 NAS 写，故 B（mark_error 吞异常）、C（连续连接错早停）
不再必要，本次不实现。

## 测试

- `test_buffering_cursor_classify`：INSERT/UPDATE → 入 pending_writes；
  SELECT → 透传（mock 真 conn）。
- `test_buffer_executemany_roundtrip`：executemany 缓冲 → flush 重放，
  params 经 json 往返类型正确（date/Decimal/None）。
- `test_flush_resumable`：重放中途模拟 NAS 抛连接错 → 已重放行已删、剩余保留，
  二次 flush 清空。
- `test_flush_order`：多语句按 seq 顺序重放（PIT 依赖 fin/earnings 先入）。
- `test_get_conn_local_first_toggle`：`set_local_first(True/False)` 切换返回类型；
  关闭后价格 pipeline 路径不受影响。
- `test_flush_empty`：无缓冲文件 → 返回 0，不报错。

## 文件清单

| 文件 | 改动 |
|------|------|
| `futu_ingest/local_buffer.py` | 新增：BufferingConnection/Cursor + flush + pending_count |
| `db.py` | 加 `_local_first` 标志 + `set_local_first()`；`get_conn()` 分支 |
| `main.py` | `cmd_futu_full/sync` 包两阶段；新增 `futu-flush` 子命令 |
| `config.py` | `FUTU_BUFFER_PATH` |
| `.gitignore` | `.futu_buffer/` |
| `tests/test_futu_local_buffer.py` | 新增测试 |
