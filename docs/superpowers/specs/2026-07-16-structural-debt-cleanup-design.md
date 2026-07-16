# 结构债清理（性能非主目标）— 设计文档

**日期:** 2026-07-16  
**状态:** 已实现（P0–P4）— 完成日 2026-07-16  
**范围:** P0–P4 结构债 / 可维护性；行为与 CLI 契约尽量不变  
**来源:** `/brainstorming` — 主目标 B；方案 1 全做  
**前置:** API 中心化、CLI 二级命令、probe/normalize 抽取、code-review residual/probe cleanup 已落地  

**工作流:**

1. 本文件 = design spec  
2. 后续 implementation plan（可按 P0–P4 拆多份或一份分 Phase）  
3. 再实现（阶段可独立 commit）

**用户锁定:**

| # | 项 | 决策 |
|---|-----|------|
| 主目标 | 结构债 / 维护成本 | 性能只做顺手低风险项（如 CN bulk sync map） |
| 方案 | 方案 1 分层手术刀串行 | 全做 P0→P4 |
| 日/周 | 代码参数化共用 | **运行与 CLI 必须分开**；禁止一次跑日+周 |
| P1 weekly 写库 | 与 daily 统一 | batch `flush_prices_and_sync`（非 per-ticker commit） |
| 跨源引擎 | 不做 | 日/周共用仅发生在各自 `apis/*` 包内 |

---

## 1. 背景

项目在 2026-07 已完成多轮模块化（`apis/*` + `jobs/*` + `core/`/`modules/`、CLI 二级命令、yf probe/normalize）。代码体量约 1.4 万行，文件普遍不大，**无明显屎山**；剩余主要是：

| 类型 | 表现 |
|------|------|
| 真复制 | `prices_us` ↔ `prices_us_weekly`；`prices_cn` ↔ `prices_cn_weekly` |
| 遗留 | `AKSHARE_*` 配置、`to_akshare_*` / `to_efinance_*` 无生产调用；`INDEX_CONFIG` HSI source 仍写 akshare |
| 同构样板 | futu `backfill_*` / `snapshot_*` 的 upsert/分页骨架重复 |
| 入口偏厚 | `main.py` 堆全部 `cmd_*`，parser 已在 `cli/` |

上轮 probe cleanup **明确 defer** 的 yf 日/周 batch 合并（P3）纳入本 spec 的 P1。  
真性能瓶颈多在上游限速与串行 sleep，**本轮不以墙钟优化为主**。

---

## 2. 目标

1. 删除无生产用途的遗留配置与转换函数，文档与元数据字段与现状一致。  
2. yfinance / tushare 各自用 **参数化 spec** 消除日/周 batch 真复制；**保留两个 public 入口**。  
3. futu 用 **轻量 helper（非 framework）** 收敛 upsert/分页样板。  
4. `main.py` 收成薄入口；命令实现进 `cli/commands_*`。  

---

## 3. 非目标

- 不为更快改 `YF_BATCH_*`、tushare 限速、futu 并发模型。  
- 不合并 CLI：`prices daily` 与 `prices weekly` 永远分开；`Pipeline.daily` 不调 weekly。  
- 不跨 `apis` 抽通用 `PriceEngine`。  
- 不新市场、新表、新数据源。  
- 不重写 futu 为巨型 framework；不引入第四顶层包。  
- 不改下游 TrendSpec / NAS 表结构。  
- P1 不碰 `prices_hk` / `prices_intraday` / `prices_index`。  
- P2 不碰 `etf_cn` / financial / valuation / `derive_periodic`。  

---

## 4. 硬约束

| 项 | 约定 |
|----|------|
| 分层 | `jobs → apis → core/modules`；禁止跨 apis 互引；jobs 禁止直接 import 上游 SDK |
| 日/周 | 共享编排用参数（interval/freq/table/`data_type`/probe/target_date）；运行时两次独立调用 |
| 验收 | 现有 pytest 绿；测试改动仅因符号搬家，不改语义 |
| 提交 | 每阶段可独立 commit；阶段之间可停 |

---

## 5. 方案选择

| 方案 | 内容 | 结论 |
|------|------|------|
| **1. 分层手术刀串行** | P0→P4 风险递增、可回滚 | **采用** |
| 2. 跨源 PriceEngine | 先造通用 runner 再迁 | 拒绝：跨源差异大，易成第二套 pipeline |
| 3. 仅死码 | 不动日周/futu | 拒绝：与主目标不对齐 |

**阶段顺序:**

```
P0 死码/遗留
 → P1 yfinance 日/周参数化 batch
 → P2 tushare 日/周参数化 + CN bulk sync map
 → P3 futu 轻量同构
 → P4 CLI / main 瘦身
```

---

## 6. P0 — 死码 / 遗留清理

### 原则

只删**已确认无生产调用路径**的符号；测试若只测死函数则一并删。

### 清单

| ID | 位置 | 动作 |
|----|------|------|
| P0.1 | `config.AKSHARE_RETRY_COUNT` / `AKSHARE_RETRY_DELAY` / `AKSHARE_REQUEST_DELAY` | 删除 |
| P0.2 | `ticker_utils`：`to_akshare_a/hk`、`from_akshare_a/hk`、`to_efinance_a/hk` | 删除（grep 仅 tests 时） |
| P0.3 | `tests/test_ticker_utils.py` 对应用例 | 删除 |
| P0.4 | `INDEX_CONFIG["HSI"]["source"]` | `"akshare"` → `"csv"`（与 `hsi_csv` 一致） |
| P0.5 | `main.py` `NO_PROXY` / eastmoney | **保留代码**，改注释为现状（非 akshare 主路径叙述） |
| P0.6 | CLAUDE.md / README 过时 akshare 限速句 | 改写为 tushare/yfinance 现状 |
| P0.7 | 本轮打开文件内旧模块名 docstring | 顺手改准；不全局无关扫改 |

### 不删

- `to_yfinance_us` / `parse_ticker` / `infer_market` 等生产路径  
- `FUTU_*` / `TUSHARE_*`、local-first 缓冲  

### 验收

```bash
rg -n 'AKSHARE_|to_akshare|from_akshare|to_efinance|from_efinance' --type py
uv run pytest tests/test_ticker_utils.py tests/test_config.py -q
uv run pytest tests/ -q
```

**风险:** 极低。

---

## 7. P1 — yfinance 日/周参数化 batch

### 差异表（合并前）

| 维度 | daily | weekly |
|------|-------|--------|
| interval | `1d` | `1wk` |
| 表 | `prices` | `prices_weekly` |
| `data_type` | `price` | `price_weekly` |
| probe | `probe_daily` | `probe_weekly` |
| 对齐日 | `last_us_trading_date()` | `_last_us_weekly_date()`（周一） |
| end | last_trading+1d | target_monday+7d |
| years | 支持 | 现状不支持（START_DATE_US） |
| 写库 | batch `flush_prices_and_sync` IGNORE | 现状 per-ticker INSERT IGNORE |

### 目标形状

新建 `apis/yfinance/prices_batch.py`（或 `batch_us.py`）：

- `UsPriceSpec`（frozen dataclass / NamedTuple）：`label`, `interval`, `data_type`, `price_table`, `probe`, `target_date`, `end_exclusive`, `on_duplicate`, `support_years`
- `run_us_equity_batch(tickers, *, spec, full_rebase, years=None)`

**Public 入口保留（jobs 不改调用面）:**

```text
prices_us.update_prices_batch(...)     → run_us_equity_batch(spec=DAILY, ...)
prices_us_weekly.update_weekly_batch(...) → run_us_equity_batch(spec=WEEKLY, ...)
```

**禁止** 单一 CLI / `Pipeline.daily` 同时拉日+周。

### 写库（已锁定）

weekly 改为与 daily 相同：`flush_prices_and_sync(price_table=..., on_duplicate=False)`。  
失败粒度对齐 daily（整 batch 写失败标记该 batch 内已解析 ok 的 ticker），不要求 per-ticker commit 比特级同序。

### 文件

| 文件 | 变化 |
|------|------|
| `apis/yfinance/prices_batch.py` | 新建 |
| `prices_us.py` / `prices_us_weekly.py` | 薄封装 |
| `jobs/market_us.py` | 不改调用面 |
| 测试 | mock 目标调整；可选 spec 不串表单测 |

### 不做

- `prices_hk` / intraday / index  
- 改 `YF_BATCH_*` 数值  
- 合并 probe 实现（只引用）  

### 验收

```bash
uv run pytest tests/test_stock_updater_us_weekly.py tests/test_yf_*.py tests/test_pipeline.py -q
rg -n "def update_prices_batch|def update_weekly_batch" apis/yfinance/
```

**风险:** 中（weekly 写库粒度变化）。

---

## 8. P2 — tushare 日/周参数化

### 差异表

| 维度 | daily | weekly |
|------|-------|--------|
| `pro_bar` freq | `D` | `W` |
| 表 / `data_type` | `prices` / `price` | `prices_weekly` / `price_weekly` |
| 拉取模型 | 均为 per-ticker（接口形状） | 同左 |

### 目标形状

新建 `apis/tushare/prices_cn_batch.py`（或 `prices_batch.py`）：

- `CnPriceSpec`：`label`, `freq`, `data_type`, `price_table`, `on_duplicate=True`
- `run_cn_equity_batch(...)`

**Public 入口:**

```text
prices_cn.update_prices_batch(...)
prices_cn_weekly.update_weekly_batch(...)
```

增量路径统一 **`get_last_sync_map` 一次**（去掉循环内 N 次 `get_last_sync`）。  
对齐日：继续 `last_cn_trading_date()`（与现状一致，不另造周对齐）。  
`BATCH_COMMIT_SIZE` + `flush_prices_and_sync` 保持。

### 文件

| 文件 | 变化 |
|------|------|
| `apis/tushare/prices_cn_batch.py` | 新建 |
| `prices_cn.py` / `prices_cn_weekly.py` | 薄入口 |
| weekly `_save_weekly_prices_batch` | 测 `price_table=` 或保留 thin wrapper |
| `jobs/market_cn.py` | 不改签名 |

### 不做

- 改 rate limit / 并行 pro_bar  
- etf / financial / valuation / derive  

### 验收

```bash
uv run pytest tests/test_stock_updater_cn_weekly.py tests/test_backfill_prices.py tests/test_market_cn.py -q
rg -n "get_last_sync\(" apis/tushare/prices_cn*.py
```

**风险:** 中。

---

## 9. P3 — futu 轻量同构

### 原则

抽 2–3 个**包内** helper，各 `backfill_*.py` 保留字段映射与表名。  
不做 `FutuBackfillFramework`、不做 22 表巨型零代码配置、不改 scope/refresh/local-first 语义。

### Helpers（`apis/futu/write_utils.py`）

| Helper | 职责 |
|--------|------|
| A `upsert_rows(table, columns, rows, update_columns)` | INSERT…ODKU + commit + 统一 log |
| B `paginate_call(client, method, code, *, list_key, page_num, **kwargs)` | next_key 分页拼 list |
| C（可选） | snapshot「batch 拉 → 变换 → upsert」；**Rule of Three**，不足三处可不抽 |

**不放 `core/`**（带 us_* 表/ODKU 业务形状）。

### 迁移顺序

1. write_utils + 单测  
2. 薄模块：profile、efficiency、actions  
3. financial（已有 statement 表驱动，换 upsert/paginate）  
4. revenue / earnings / shareholders（只换骨架）  
5. snapshot_*：仅循环 ≥3 处相同再引入 C  

`concurrency.ticker_stream` / `run_streams` / `batch_with_bisect` / `client` 限频 / `orchestrator.run_sync` **保留**。  
`backfill_all(tickers, force=False) -> dict` 签名与返回字段尽量不变。

### 不做

- 合并 snapshot 业务字段与 refresh 配置  
- 强行合并 shareholders 多表到单文件  

### 验收

```bash
uv run pytest tests/test_futu_*.py -q
rg -n "ON DUPLICATE KEY UPDATE" apis/futu/
```

**风险:** 中高（字段映射）— 禁止顺手改列；逐文件迁。

---

## 10. P4 — CLI / main 瘦身

### 目标

- `main.py`：env/proxy、logging、legacy argv、parser、dispatch、`sys.exit`  
- `cmd_*` → `cli/commands_*.py`

### 建议模块

```text
cli/
  parser.py              # 已有
  deprecate.py           # 已有
  commands_prices.py     # daily / weekly / rebase / intraday
  commands_tushare.py
  commands_futu.py
  commands_db.py
  commands_meta.py       # init / status
```

单文件 `cli/commands.py` 仅当总行数明显更小时可选；默认按域拆分。

### 规则

- 纯搬家；**argv / 返回码不变**  
- CLI 层不写新采集逻辑  
- `main` 对 `cmd_*` **薄 re-export**，避免 `tests/test_cli.py` 与外部 `import main` 碎掉  
- 保持 argparse，不引入 Click/Typer  

P4 **最后**做，减少与 P1–P3 冲突。

### 文档

- README 架构树：`cli/commands_*`；`main.py` 标入口  
- CLAUDE.md：命令字符串不变；可选「实现见 cli/」  
- 本 spec 落地后按阶段勾「已实现」  

### 验收

```bash
uv run pytest tests/test_cli.py tests/ -q
# 人手：main.py --help 与子命令 help 与改前一致
```

**风险:** 低。

---

## 11. 跨阶段验收契约

| 契约 | 要求 |
|------|------|
| CLI argv | 二级命令与 flag 不变 |
| 日/周分离 | `Pipeline.daily` 不调 weekly；无合并采集入口 |
| 写表 | 表名/列/ODKU·IGNORE 与各阶段设计一致 |
| futu scope | `all/other/daily/weekly/financial/...` 与 refresh 不变 |

**全量测试:**

```bash
uv run pytest tests/ -q
```

**结构检查:**

```bash
rg -n 'AKSHARE_|to_akshare|to_efinance' --type py
rg -n 'def update_prices_batch|def update_weekly_batch' apis/
# jobs 不 import SDK；apis 不跨子包互引
```

---

## 12. 风险总表

| 阶段 | 风险 | 缓解 |
|------|------|------|
| P0 | 极低 | grep + 单测 |
| P1 | 中 | weekly→batch flush 与 daily 对齐；mock flush |
| P2 | 中 | map 单测 |
| P3 | 中高 | 禁止改列；逐文件；futu 全测 |
| P4 | 低 | re-export；cli 测 |

---

## 13. 交付物

1. 本 design spec（本文）  
2. implementation plan（下一步 `writing-plans`；可 P0–P4 分 Phase）  
3. 代码按阶段 commit  

---

## 14. 依赖与非目标再确认

- 不依赖新基础设施或 DB migration。  
- 不优化限速与 batch 大小。  
- 不新数据源。  
- 实现阶段若发现某 `to_akshare_*` 仍有生产引用：P0 改为保留该符号并在 plan 记「保留原因」，不硬删。  
```
