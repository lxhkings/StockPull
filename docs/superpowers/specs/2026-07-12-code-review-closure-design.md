# Code-review 残留债收口 — 设计文档

**日期:** 2026-07-12  
**状态:** 已实现  
**范围:** 单 spec；修上一轮 `/code-review` 六项残留，**不**引入新数据源 / 新表 / 新市场  
**来源:** 分支相对 `origin/main` 的 4 commits 审查 + brainstorming 决策  
**前置:** `docs/SPEC_code_review_followup.md`（Phase 0–4 已落地；本文件为其 closure）

**工作流（superpowers）:**  
1. 本文件 = design spec  
2. Plan：`docs/superpowers/plans/2026-07-12-code-review-closure.md`  
3. 再实现  

**用户锁定（全部 A / 方案 1）:**

| # | 项 | 决策 |
|---|-----|------|
| 1 | daily 默认拉满 15m+1h | **拆开**：`Pipeline.daily` 不调 intraday |
| 2 | HK weekly raise vs Protocol | **no-op** `return {}` |
| 3 | probe 限速静默路径 | **删假语义** + **三处对齐**：empty → `no_data`；限速仅 except 字符串；**intraday 补齐** `rate_limit` 分支与批量 skip |
| 4 | purge_index 非事务 | **单连接事务**包一组 DELETE |
| 5 | hasattr(render) / 死 `cmd_tushare_sync` | **本轮收口** |
| 6 | prices_index 测 + SPEC 归档 | **本轮收口** |
| 打包 | — | **单次外科 PR**，不重构能力模型 |

---

## 1. 背景

上一轮 follow-up（CSI800 下线、`prices_index` 归位、Protocol 扩方法、CLI rewrite、`backfill_new` 合并）把结构债清掉大半，但留下：

1. **日线与分钟线焊在一起**：为消灭 `hasattr`，`Pipeline.daily` 固定调 `intraday()`，且 US 默认变成 `15m+1h`（改前 daily 内默认仅 `1h`）。协议整洁被兑换成更重的默认行为。  
2. **能力模型不一致**：CN/HK `intraday` no-op，HK `weekly` 却 `raise NotImplementedError`，Protocol 签名撒谎。  
3. **probe 语义不对称**：日线/周线 except 可返回 `rate_limit`；intraday probe 不能，且批量入口不处理该 status。empty 从不推断限速（正确），但三处契约未对齐。  
4. **`purge_index` 多表非原子**：`execute()` 每次独立 commit。  
5. **CLI 小残留**：`_run_buffered` 内联 `hasattr(render)`；`cmd_tushare_sync` 已无 dispatch 入口。  
6. **测试/文档**：`prices_index` 仅测符号表+委托；旧 SPEC 头仍写「剩余项」。

本轮目标：行为边界正确、协议诚实、admin 原子、测/文档对齐——**删耦合，不加概念**。

---

## 2. 非目标

- 不实现港股周线 / CN 分钟线  
- 不引入 `supports_*` / optional Protocol 子集  
- 不加 `prices daily --with-intraday`  
- 不增强 `download_with_retry` 做日志捕获限速  
- 不新增通用 `transaction()` helper（仅 purge 内联单连接）  
- 不改 NAS 表结构、不改 yfinance/tushare 抓取算法本体  

---

## 3. 架构边界（沿用 CLAUDE.md）

```
main.py     → jobs, apis, core, modules
jobs/*      → apis.*, core, modules   ❌ SDK
apis/*      → core, modules, config
modules/*   → core, config
```

本轮触点：

| 层 | 文件 |
|----|------|
| jobs | `pipeline.py`, `market_hk.py`（+ 文档触及 market_us 默认说明） |
| apis | `prices_us.py`, `prices_us_weekly.py`, `prices_intraday.py`（docstring/测为主） |
| modules | `db_admin.py`（purge 事务） |
| main/cli | `main.py`（`_format_run_result`、删 `cmd_tushare_sync`） |
| docs/tests | CLAUDE/README、SPEC 归档、相关 tests |

---

## 4. 设计分项

### 4.1 #1 Daily 与 Intraday 拆开

**语义**

| 入口 | 做什么 | 不做什么 |
|------|--------|----------|
| `prices daily` → `Pipeline.daily()` | 成分/列表、日线增量、指数/ETF 日线 | **不**拉分钟线 |
| `prices intraday` → `market_us.intraday()` | 美股 15m/1h，默认 `SUPPORTED_INTERVALS` | 不经 Pipeline.daily |

**代码**

1. `jobs/pipeline.py`  
   - 删除 Step 4：`self.m.intraday()` 及对应 log  
   - 步骤：1 成分 → 2 增量 → 3 指数/ETF 价 → complete  
   - 模块 docstring：去掉「intraday always / pulls 15m/1h」；写明分钟线仅 CLI  
   - **Protocol 保留 `intraday()`**（CLI 与单测仍用；CN/HK 继续 no-op）

2. `jobs/market_us.intraday`  
   - 默认仍 `SUPPORTED_INTERVALS`；签名不变  
   - 仅被 `main.cmd_intraday`（及直接调用）使用

3. `main.cmd_intraday` — 无行为变化

4. 文档：`CLAUDE.md`、`README.md` Pipeline 步骤与「每周/按需命令」表对齐：daily 不含分钟线；分钟线单独 `prices intraday`

**测试**

- `tests/test_pipeline_intraday.py` → 断言 daily **不**调用 `intraday`（改名/改写）  
- `tests/test_pipeline.py` 若有 mock 调用次数，对齐  
- CLI / `test_market_us_intraday` 保持 CLI 默认 15m+1h

**验收：** daily 路径零 `intraday` 调用；`prices intraday` 默认 interval 不变。

---

### 4.2 #2 HK weekly → no-op

**契约：** 未实现能力 = 返回空 dict，不 raise（与 CN/HK `intraday` 一致）。

| 位置 | 动作 |
|------|------|
| `jobs/market_hk.weekly` | `return {}`；docstring 标明未实现 + CLI 未开放 hk |
| `cli/parser.py` | **不改**（weekly 仍 `us\|cn`） |
| Protocol | **不改** |

**测试：** `tests/test_market_hk.py` — `weekly()` 返回 `{}`、不 raise。

---

### 4.3 #3 Probe 语义：删假合同 + 三处真正对齐

**现状（不对称，实现前必读）：**

| Probe | empty → | except 限速字符串 → `rate_limit` |
|-------|---------|----------------------------------|
| `prices_us._test_aapl_data` | `no_data` | **有** |
| `prices_us_weekly._test_aapl_weekly` | `no_data` | **有** |
| `prices_intraday._test_aapl_intraday` | `no_data` | **无**（一律 `error`）；docstring 也未列 `rate_limit` |

「删假合同」= 不从 empty/日志推断限速。  
「三处统一」= 上表四态行为一致，**不是**「只改文档、假定限速分支已有」。

**目标语义（三处相同）：**

| 情况 | status |
|------|--------|
| 有目标日/有效数据 | `ok` |
| 空 DF / 无目标日 | `no_data` |
| 异常且文案含 `RateLimit` / `Too Many Requests` | `rate_limit` |
| 其他异常 | `error` |

**做（代码 + 文档）：**

1. **`prices_us` / `prices_us_weekly`：** except 限速分支**保留**；docstring 与上表对齐；去掉任何「empty 可推断限速」表述（若有）。  
2. **`prices_intraday._test_aapl_intraday`（代码必改）：**  
   - except 补齐与日线/周线**相同**的字符串匹配 → `rate_limit`，其余 → `error`  
   - docstring Returns 增加 `"rate_limit"`  
3. **`update_intraday` 批量入口（代码必改）：** 今日只处理 `no_data` / `error`；`rate_limit` 会落到 `latest_date is None` 继续跑。补：

   ```text
   if status == "rate_limit":
       log.warning(...限速，跳过...)
       return {}
   ```

   与 `no_data` / `error` 一样整批 skip。

**不做：**

- 不恢复 yfinance logging Handler  
- 不改 `download_with_retry`（限速分类仍在各 probe 的 except，不抽到 client）  
- 不为 empty 发明限速  

**测试：**

- empty → `no_data`（三处一致；无 empty→rate_limit 断言）  
- mock `download_with_retry` raise 含 `RateLimit` / `Too Many Requests` → probe 返回 `rate_limit`  
- **intraday：** 上述 except 分支 + `update_intraday` 遇 `rate_limit` 返回 `{}` 不继续批量  

**成功标准补充：** 三处 probe 对限速异常均返回 `rate_limit`；intraday 批量入口识别并 skip。

---

### 4.4 #4 `purge_index` 事务

`core.db_client.execute()` 每次新连接 + commit，**不能**用于多语句原子删除。

**`purge_index(..., dry_run=False)`：**

```
validate index_id
conn = get_conn()
try:
    for table in _INDEX_PURGE_TABLES:   # 常量白名单，非用户拼接
        DELETE FROM {table} WHERE index_id=%s
        record rowcount
    conn.commit()
    return deleted
except:
    conn.rollback()
    raise
finally:
    conn.close()
```

| 项 | 决定 |
|----|------|
| dry_run | 仍 `count_index_rows`（只读） |
| 通用 transaction helper | **不**抽到 core（YAGNI） |
| CLI | `cmd_purge_index` 不变；异常上抛 |

**测试（`tests/test_db_admin.py`）：**

- 成功：同一 conn 上 N 次 DELETE + **一次** commit  
- 中途失败：rollback，无成功 commit  

---

### 4.5 #5 CLI 收口

1. **`main._format_run_result(result) -> str`**  
   - `render = getattr(result, "render", None)`；`callable(render)` 则 `return render()`  
   - 否则 `return str(result)`  
   - `_run_buffered` 只 `print(_format_run_result(result))`  
   - 不引入 typing Protocol（duck 单点即可）

2. **删除 `cmd_tushare_sync`**  
   - `_dispatch_tushare` 已对 sync 调 `cmd_tushare_backfill(..., start=None)`  
   - `tests/test_main_tushare_backfill.py`：`test_tushare_sync_passes_no_start` 改为经 `main(["tushare","sync",...])` 断言落到 `cmd_tushare_backfill(..., start=None)`

---

### 4.6 #6 测试补齐 + SPEC 归档

**`prices_index` 写路径（mock `query` / `download_with_retry` / `execute` / `last_us_trading_date`）：**

| 场景 | 期望 |
|------|------|
| last_date ≥ last_trading | 不下载、不 execute |
| 有增量 close | `INSERT IGNORE` 被调用，返回汇总行数 |
| 某 symbol 下载 raise | skip 该 symbol，整批不炸 |

可落在 `tests/test_us_index_price.py`。

**文档：**

| 文件 | 动作 |
|------|------|
| `docs/SPEC_code_review_followup.md` | 头改为「已完成 / 由 closure design 接替」；或移到 `docs/superpowers/specs/` 并链到本文件；禁止「剩余项」误导 |
| `CLAUDE.md` / `README.md` | 与 §4.1 一致 |
| 本文件 | 实现后状态可改为「已实现」 |

---

## 5. 实现顺序（建议 plan 任务序）

1. #1 pipeline 拆 intraday + 测 + 文档步骤  
2. #2 HK weekly no-op + 测  
3. #3 probe docstring/测对齐  
4. #4 purge 事务 + 测  
5. #5 `_format_run_result` + 删 `cmd_tushare_sync` + 测  
6. #6 prices_index 写路径测 + SPEC 归档  
7. 全量 `uv run pytest tests/ -q`

每步可独立绿测；优先 #1（唯一行为边界变化）。

---

## 6. 风险与缓解

| 风险 | 缓解 |
|------|------|
| 运维只跑 `prices daily` 指望顺带分钟线 | README/CLAUDE 写明；需分钟线加 `prices intraday`（cron 两条） |
| purge 事务与连接池 autocommit 行为差异 | 显式 commit/rollback；测 mock 验证调用序 |
| 删 `cmd_tushare_sync` 破坏外部 import | 仓库内仅 test 引用；grep 确认无其他 import |

---

## 7. 成功标准

- [x] `Pipeline.daily` 不调用 `intraday`  
- [x] `market_hk.weekly()` → `{}`  
- [x] 三处 probe：empty = `no_data`；限速仅 except 字符串 → `rate_limit`（含 **intraday 补齐**）  
- [x] `update_intraday` 对 `rate_limit` 整批 skip  
- [x] `purge_index(dry_run=False)` 单连接 commit/rollback  
- [x] 无 `cmd_tushare_sync`；`_run_buffered` 经 `_format_run_result`  
- [x] `prices_index` 写路径有测；旧 SPEC 不再标「剩余」  
- [x] `uv run pytest tests/ -q` 全绿  
- [x] CLAUDE/README Pipeline 描述与实现一致  

---

## 8. 与既有文档关系

```
docs/SPEC_code_review_followup.md     # Phase 0–4 执行记录 → 归档/接替
docs/superpowers/specs/
  2026-07-12-code-review-closure-design.md   # 本文件（closure）
docs/superpowers/plans/
  2026-07-12-code-review-closure.md          # 下一步 writing-plans
```
