# Spec: Code-review 未决项跟进（已完成 / 已归档）

> **状态：已完成。** Phase 0–4 已落地。  
> **Closure：** `docs/superpowers/specs/2026-07-12-code-review-closure-design.md`  
> **Plan：** `docs/superpowers/plans/2026-07-12-code-review-closure.md`  
> 本文仅保留历史执行记录，**不再作为待办**。
>
> 来源：`/code-review`（apis+jobs 落地后结构审查）  
> 已完成：CSI800 下线（全 A + 行业 ETF）、`db purge-index` 组件化；Phase 1–4 见下文历史记录。

## 目标（历史）

在**不改变对外数据语义**的前提下，消除审查中的结构债：

1. 采集逻辑回到 `apis/*`，`jobs/*` 只编排  
2. `MarketModule` 协议与实现一致，去掉 `hasattr` 特判  
3. Intraday 单一入口与默认 interval 一致  
4. 删死代码与假抽象（能删概念就删）  
5. CLI 双轨、buffer 编排重复、yfinance 探测绕 client（Phase 4，已落地）

## 非目标（历史）

- 不改 NAS 表结构  
- 不引入新数据源 / 新市场  
- CLI argv rewrite 已在 Phase 4 / closure 落地
## 分层硬约束（复用 CLAUDE.md）

```
jobs → apis → core/modules
apis 禁止 import jobs；jobs 禁止直接 import 上游 SDK
yfinance 调用 MUST 走 apis.yfinance.client
```

---

## Phase 0 — 已完成（对照）

| 项 | 结果 |
|---|---|
| CSI800 成分 + 指数价 | 删除；CN = 全 A + 行业 ETF |
| DB 历史 CSI800 | NAS 已 purge |
| `db purge-index` | `modules.db_admin.purge_index` + CLI |

---

## Phase 1 — US 指数价归位 `apis/yfinance`（P0）

### 问题

`jobs/market_us.update_index_price` 内含 `download_with_retry` + DataFrame 解析 + `INSERT index_prices`，与 CN 的 `apis.tushare.etf_cn` 模式不对称。

### 方案

| 文件 | 动作 |
|---|---|
| `apis/yfinance/prices_index.py` | **新建** `update_index_prices() -> int`（原 market_us 逻辑原样迁入） |
| `jobs/market_us.py` | `update_index_price()` 一行委托 |
| `tests/test_us_index_price.py` | 测 `prices_index` 符号列表 + 委托；禁止 `inspect` 锁死 jobs 源码 |

### 验证

```bash
uv run pytest tests/test_us_index_price.py tests/test_market_us_intraday.py -v
rg -n "download_with_retry" jobs/   # 期望 0
```

---

## Phase 2 — Protocol + Intraday 单路径（P0）

### 问题

1. Protocol 只有 daily 五方法；文档写 rebase/weekly/intraday，实现靠旁路  
2. Pipeline `hasattr(..., "intraday")` 是特判  
3. CLI `prices intraday` 默认 `15m+1h`；`market_us.intraday()` 默认仅 `1h`  
4. CLI 直调 `apis.yfinance`，绕过 market 适配层  

### 方案

**Protocol（`jobs/pipeline.py`）显式包含：**

```
update_index / list_active_tickers / backfill_new / incremental /
update_index_price / rebase / weekly / intraday
```

| 市场 | weekly | intraday |
|---|---|---|
| US | 实现 | 实现，默认 `SUPPORTED_INTERVALS` |
| CN | 实现 | no-op `return {}` |
| HK | `NotImplementedError`（CLI 本就不开放 hk weekly） | no-op `return {}` |

**Pipeline Step 5：** 始终 `self.m.intraday()`（无 hasattr）。

**CLI：** `cmd_intraday` → `jobs.market_us.intraday(intervals=..., full_rebase 透传)`  
（若 `update_intraday` 需 rebase，由 market_us 转发。）

**默认 interval 单一真相：** `apis.yfinance.prices_intraday.SUPPORTED_INTERVALS`。

### 验证

```bash
uv run pytest tests/test_pipeline_intraday.py tests/test_market_us_intraday.py tests/test_cli.py -v
rg -n "hasattr" jobs/pipeline.py main.py  # 无 market 能力探测
```

---

## Phase 3 — 小清理（P1）

| 项 | 动作 |
|---|---|
| `main.cmd_daily` `ImportError: not yet implemented` | 删除 try；三市场均存在 |
| `main.cmd_rebase` `hasattr(rebase)` | 删除；三市场均有 rebase |
| `jobs/market_hk` 未用 `get_conn` | 删 import |
| `jobs/market_cn.update_index` 手写 cursor 计数 | 改用 `query` |
| pipeline docstring | 删「US rebase NotImplemented」错误叙述 |
| HK `update_index_price` 恒 0 | 保留 no-op，docstring 标明「暂不采」 |

### 验证

```bash
uv run pytest tests/test_market_cn.py tests/test_market_hk.py tests/test_pipeline.py -v
```

---

## Phase 4 — 已落地

| 项 | 实现 |
|---|---|
| CLI 旧入口双轨 | `cli.deprecate.rewrite_legacy_argv`；parser 无 SUPPRESS 镜像；main 无 legacy if 链 |
| tushare/futu buffer+flush | `main._run_buffered` |
| `backfill_new` ≡ `incremental` | Protocol/markets 删除 `backfill_new`；Pipeline 单步 `incremental` |
| yfinance 探测 `yf.download` | `prices_us` / `prices_us_weekly` / `prices_intraday` 探测与 single 走 `download_with_retry` |

---

## 成功标准

- [x] `jobs/` 无 `download_with_retry` / `get_client` / SDK  （Phase 1–3）
- [x] Pipeline 无 `hasattr` 能力探测  
- [x] Intraday 默认 interval 与 CLI 一致  
- [x] 全量 `uv run pytest tests/ -q` 绿（407 passed，Phase 4 后）
- [x] README/CLAUDE 与实现一致（CN 全 A；US 指数价在 apis）  

### 落地进度（历史）

| Phase | 状态 |
|---|---|
| 0 CSI800 / purge-index | 已完成 |
| 1 US prices_index | 已完成 |
| 2 Protocol + intraday | 已完成 |
| 3 小清理 | 已完成 |
| 4 CLI rewrite / buffer / yf probe / backfill 合并 | 已完成 |
| Closure（daily/intraday 拆分等） | 见 `2026-07-12-code-review-closure-design.md` |

## 风险（历史）

| 风险 | 缓解 |
|---|---|
| daily 流水线突然跑满 15m+1h 变慢 | closure：daily 与 intraday 拆开 |
| 迁 prices_index 测挂 | 保持函数语义与 SQL 不变；写路径 mock 测已补 |
