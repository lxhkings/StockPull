# Code-review 残留清理 — 设计文档

**日期:** 2026-07-15  
**状态:** Plan 1 已实现；Plan 2 待做  
**范围:** 上一轮 `/code-review` 五项结构债；**不**引入新数据源 / 新表 / 新市场  
**来源:** `/code-review` 严格审查 + brainstorming  
**前置:** `docs/superpowers/specs/2026-07-12-code-review-closure-design.md`（已实现）

**工作流:**

1. 本文件 = design spec  
2. 两份 implementation plan（见 §6 打包）  
3. 再实现（个人开发，不强制 PR；按 plan 顺序落地 + 测）

**用户锁定:**

| # | 项 | 决策 |
|---|-----|------|
| 打包 | A–E 体量 | **方案 1：两 plan** — Plan 1 = A+C+D+E；Plan 2 = B |
| D | CN `update_index` 诚实 | **真 set diff**（与 US/HK 同契约；未口头改口时按此执行） |
| 流程 | PR | 不强制；可顺序 commit 到 `main` |

---

## 1. 背景

Closure 已落地：`prices_index` 归位、daily/intraday 拆开、HK weekly no-op、probe `rate_limit` 对齐、`purge_index` 事务、CLI 二级命令。审查仍指出：

| ID | 问题 | 体量 |
|----|------|------|
| **A** | NaN→None 清洗散落；工作区 `transform_lists._or_none` 是局部创可贴 | 小 |
| **B** | yfinance 日/周/分钟三套 probe + OHLCV normalize 近重复 | 大 |
| **C** | CLI 旁路：`--etf-only` 直调 `apis.tushare`；`intraday` 硬编码 `market_us` | 中 |
| **D** | CN `update_index` 恒 `return [], inserted, 0`，Pipeline「新票全量」日志死分支；`added` 算了又丢 | 中 |
| **E** | `db_admin.get_all_stocks` / `get_tickers_without_prices` 死代码（stooq 时代） | 极小 |

目标：**行为语义不变**（抓取结果、表写入、CLI 对外 argv 不变），删除重复概念与假契约，逻辑归回正确分层。

---

## 2. 非目标

- 不实现港股周线 / CN 分钟线 / 新市场  
- 不引入 `supports_*` 能力矩阵或 Protocol 子集拆分  
- 不改 NAS 表结构、不改 tushare/yfinance 业务算法（起点、复权、batch 大小等）  
- 不把 `or_none` 强行替换所有 `to_float`/`to_date` 内部逻辑（二者已自处理 NaN）  
- 不增强 `download_with_retry` 用日志推断限速  
- 不强制 GitHub PR / stack；plan 仅作落地顺序与验收清单  

---

## 3. 架构边界（沿用 CLAUDE.md）

```
main.py     → jobs, apis, core, modules, config
jobs/*      → apis.*, core, modules, config   ❌ 上游 SDK
apis/*      → core, modules, config           ❌ jobs；❌ 跨 apis 子包互引
core/*      → stdlib / 第三方 / config
modules/*   → core, config
```

| 项 | 归属层 | 主要文件 |
|----|--------|----------|
| A `or_none` | `core/` + 调用方 | `core/http_utils.py`；`apis/tushare/transform_*`；`modules/index_base.py`；可选 futu/static 同行替换 |
| B probe/normalize | `apis/yfinance` | 新建 `probe.py` / `normalize.py`（或等价命名）；改 `prices_us` / `prices_us_weekly` / `prices_intraday`；`prices_index` 尽量复用 normalize |
| C CLI 收回 | `main` + `jobs` | `main.py`；`jobs/market_cn.py`；测 `test_cli*` |
| D CN diff | `jobs` | `jobs/market_cn.py`；相关 market/pipeline 测 |
| E 死代码 | `modules` | `modules/db_admin.py` |

---

## 4. 设计分项

### 4.1 A — `core.http_utils.or_none` 统一 NaN 清洗

**问题:**  
pandas/`iterrows` 把缺失变成 `float('nan')`，MySQL 拒收。日期路径已有 `to_date`（内部 `pd.isna`）；字符串/通用标量路径多处私有 `_null` / `_or_none` / 行内 `None if pd.isna`。

**方案:**

1. 在 `core/http_utils.py` 增加：

   ```python
   def or_none(value):
       """缺失值（None / NaN / NaT / pd.NA）→ None；其余原样返回。"""
       if value is None:
           return None
       try:
           if pd.isna(value):
               return None
       except (TypeError, ValueError):
           pass
       return value
   ```

   - 与 `to_date` / `to_float` 同级，**纯函数、零 I/O**。  
   - 不把 list/dict 整棵清洗；调用方对标量使用。  
   - 实现须对「不可 `pd.isna` 的类型」安全（try/except 或类型守卫），避免炸非标量误用。

2. **迁移（最低集合，Plan 1 必做）:**

   | 位置 | 动作 |
   |------|------|
   | 工作区 `apis/tushare/transform_lists.py` | 删私有 `_or_none`；`transform_etf_basic` / `transform_hk_connect` 的 name 等字符串字段用 `or_none`；日期仍 `to_date` |
   | `modules/index_base.register_stocks` | 内嵌 `_null` → `or_none` |
   | `apis/tushare/transform_shareholder_return._to_str` | NaN 分支可 `or_none` 后再 `str`，或保留专用 `_to_str` 但内部调用 `or_none` |
   | `apis/tushare/backfill_lists._to_str` | 若仍使用则同上；否则删重复 |

3. **同模式可选替换（Plan 1 顺手、不扩 scope）:**  
   `transform_financial` / `transform_valuation` / `russell_ishares` / futu 中与 `or_none` **语义完全相同**的一行式，改为调用 canonical；**禁止**为「统一」而改写 float 强制转换逻辑（valuation 的 `float(r[c])` 仍保留）。

4. **测试:**

   - `tests/test_http_utils.py`：`or_none(None)` / `float('nan')` / `pd.NA` / 正常 str/int 原样。  
   - `tests/test_transform_lists.py`：ETF 字段含 `nan` 时对应 tuple 位为 `None`（覆盖当前工作区补丁动机）。

**成功标准:** 全仓 transform 路径不再为「仅 NaN→None」新增私有 helper；ETF NaN 写入可测。

---

### 4.2 C — CLI 旁路收回 market 层

**问题:**

1. `cmd_rebase(..., etf_only=True)` 在 `main` 直调 `apis.tushare.etf_cn.update_etf_prices`。  
2. `cmd_intraday` `from jobs import market_us` 硬编码，与 `_import_market` 模式不一致。

**方案:**

1. **`--etf-only`:**  
   - 在 `jobs/market_cn.py` 增加明确入口，例如：

     ```python
     def rebase_etf(*, full_rebase: bool = True) -> int:
         from apis.tushare.etf_cn import update_etf_prices
         return update_etf_prices(full_rebase=full_rebase)
     ```

   - 或扩展现有 `update_index_price` 支持 `full_rebase` 参数并文档化；**优先独立 `rebase_etf`**，避免污染 daily 用的 `update_index_price()` 无参签名。  
   - `main.cmd_rebase`：`etf_only` 时 `_import_market("cn")`（或已选 market 校验为 cn）后调 `mod.rebase_etf()`；非 cn 仍 stderr + exit 1。  
   - **不**把 `rebase_etf` 塞进 `MarketModule` Protocol（仅 CN 有；避免又一次全员 no-op）。

2. **`prices intraday`:**  
   - `cmd_intraday` 改为 `_import_market("us").intraday(...)`（或 `market="us"` 常量 + `_import_market`）。  
   - 仍仅支持美股；不在本轮开放 `--market`。  
   - `SUPPORTED_INTERVALS` 展示可继续从 `apis.yfinance.prices_intraday` 读（展示常量，非采集逻辑）。

3. **测试:**  
   - 更新 `tests/test_cli_rebase_etf.py`：mock `jobs.market_cn.rebase_etf`（或等价路径），断言 **不再** 直接 patch `apis.tushare.etf_cn` 作为 CLI 唯一触点（允许 market 内再调 apis）。  
   - CLI/intraday 相关测：仍落到 `market_us.intraday`。

**成功标准:** `main.py` 的 rebase-etf / intraday 路径不直调采集实现细节以外的「业务编排」；etf rebase 经 `market_cn`。

---

### 4.3 D — CN `update_index` 真 set diff

**问题:**  
恒返回 `[], inserted, 0`；count 差 `added` 仅打日志；Pipeline 对 `new_tickers` 的 full-history 提示对 CN 永不触发。

**方案（真 set diff）:**

1. `update_index` 流程：

   ```
   prev = set(list_active_tickers())   # 或等价 SQL 一次取 ticker 集合
   inserted = backfill_stocks_a()      # 现有 upsert
   curr = set(list_active_tickers())
   added = sorted(curr - prev)
   removed = len(prev - curr)
   return added, inserted, removed
   ```

2. **语义说明（docstring 必写）:**  
   - `inserted` 仍为 `backfill_stocks_a` 返回值（upsert 影响行语义保持现状，不重新定义）。  
   - `added` / `removed` 基于 **stocks 表可见 A 股集合** 前后差，不是指数成分 `constituent_changes`。  
   - 新票全量仍依赖 **空 `sync_log` + `incremental`**；本改动不新增单独 backfill 步骤。  
   - `list_active_tickers` 的 `index` 参数仍忽略。

3. **性能:** 全 A 约数千 ticker，两次 list 可接受；若已有 count SQL，可删掉仅用于假日志的 count 差，或保留 count 日志但以 set diff 为准。

4. **测试:**  
   - mock `backfill_stocks_a` + `query`/`list_active_tickers`，构造 prev/curr 差集，断言返回 `added` 列表与 `removed` 计数。  
   - 无新增 → `added == []`，`removed == 0`。

**成功标准:** CN 与 US/HK 一样，Pipeline 在确有新 ticker 时能打出 new-tickers 日志；契约不再对 CN 撒谎。

---

### 4.4 E — 删除 `db_admin` 死代码

**方案:**

- 删除 `get_all_stocks`、`get_tickers_without_prices` 及其 docstring。  
- 全仓 `rg` 确认零引用（含 tests）。  
- 不删 `stooq_ticker` 列（表结构非目标）。

**成功标准:** 两函数不存在；测试全绿。

---

### 4.5 B — yfinance probe + OHLCV normalize 抽出（Plan 2）

**问题:**  
`prices_us` / `prices_us_weekly` / `prices_intraday` 各有 `_test_aapl_*`、`_yf_symbol`、`_normalize_*_frame`；限速字符串判定与 MultiIndex 降列重复。上轮已证明改契约要动三处。

**方案（行为不变的抽取）:**

1. **新建（命名可微调，职责固定）:**

   | 模块 | 职责 |
   |------|------|
   | `apis/yfinance/ticker_utils.py`（已有则扩展） | 统一 `_yf_symbol`：`BRK.B` → `BRK-B`；删除三文件私有副本 |
   | `apis/yfinance/normalize.py` | 日/周：`sub` DataFrame → 标准列 `ticker, date, open, high, low, close, volume`；分钟：含 `interval` + `datetime`。共享 MultiIndex/lower/date 列探测 |
   | `apis/yfinance/probe.py` | AAPL readiness：日线 `probe_daily(target_date)`、周线 `probe_weekly(target_monday)`、分钟 `probe_intraday(interval)`；统一 status：`ok` / `no_data` / `rate_limit` / `error` |

2. **契约（与现网对齐，禁止静默改语义）:**

   - empty DataFrame → `no_data`（**不**当 rate_limit）。  
   - `rate_limit` 仅 except 消息含 `RateLimit` / `Too Many Requests`。  
   - 批量入口对 `rate_limit` / `no_data` / `error` 的 skip 行为保持各文件现状。  
   - 全部经 `apis.yfinance.client.download_with_retry`。

3. **`prices_index`:**  
   - 列 lower / close 提取尽量调用 normalize 的轻量 helper；不强制走 AAPL probe（指数价无 probe 步骤，保持现状）。

4. **测试:**  
   - 现有 probe/normalize/batch 测改为 import 新模块或继续测 public `update_*`（行为金丝雀）。  
   - 可补 `tests/test_yf_normalize.py` / `test_yf_probe.py` 纯函数测，避免三份拷贝回归。

5. **非目标（Plan 2 仍不做）:**  
   - 不合并日线/周线为单一 `update_prices_batch(interval=)` 上帝函数。  
   - 不改 batch 大小、delay、表名。

**成功标准:** 三 prices 文件不再各自维护 `_yf_symbol` 与近同构 normalize/probe；`rg '_test_aapl|_normalize_yf_frame|_normalize_weekly_frame'` 仅剩委托或删除；相关 pytest 绿。

---

## 5. 错误处理与风险

| 风险 | 缓解 |
|------|------|
| `or_none` 对奇怪类型抛错 | try/except `pd.isna`；单测覆盖 |
| CN set diff 把「名称变更」当成 remove+add | stocks 主键是 ticker；仅 ticker 进出集合才 diff；可接受 |
| CLI 测 brittle mock 路径 | 测「调用 market 层」而非 apis 细节 |
| Plan 2 抽取时改掉限速语义 | 金丝雀：现有 rate_limit 测必须保留并通过 |
| 工作区 `transform_lists` 未提交补丁 | Plan 1 一并纳入；用 canonical `or_none` 替换私有函数 |

---

## 6. 打包与落地顺序

**个人开发：两 plan，顺序执行。**

### Plan 1 — 边界债（A + C + D + E）

建议 commit 粒度（可合并，但顺序建议）:

1. E 删死代码  
2. A `or_none` + transform/index_base 迁移 + 测  
3. D CN set diff + 测  
4. C CLI→market + 测  

**验收:**

```bash
uv run pytest tests/test_http_utils.py tests/test_transform_lists.py \
  tests/test_market_cn.py tests/test_cli_rebase_etf.py tests/test_db_admin.py \
  tests/test_cli.py -v
rg -n "def get_all_stocks|def get_tickers_without_prices" modules/
rg -n "def _or_none" apis/tushare/transform_lists.py   # 期望 0
rg -n "update_etf_prices" main.py                      # 期望 0（经 market_cn）
```

### Plan 2 — yfinance 抽取（B）

1. `ticker_utils` 统一 symbol  
2. `normalize.py` + 日/周/分钟改用  
3. `probe.py` + 三入口改用  
4. 测与文档一行（README/CLAUDE 若提及内部函数则更新）

**验收:**

```bash
uv run pytest tests/test_intraday_probe_rate_limit.py \
  tests/test_stock_updater_us_weekly.py tests/test_us_index_price.py \
  tests/test_intraday_updater_us.py tests/test_market_us_intraday.py -v
# 私有三副本消失或仅 re-export
```

---

## 7. 文档

- 本 spec：实现过程中状态可改为「部分实现 / 已实现」。  
- Plan 文件：`docs/superpowers/plans/2026-07-15-code-review-residual-plan1.md` 与 `...-plan2.md`（writing-plans 阶段生成）。  
- 不强制改 README，除非 CLI 行为说明与实现不一致（本轮预期一致）。

---

## 8. 成功标准（总）

| 标准 | 验证 |
|------|------|
| NaN 字符串字段有 canonical `or_none` | 单测 + 无新私有 `_or_none` |
| CLI etf/intraday 经 market | main 无直调 etf 采集；intraday 经 `_import_market`/`market` 适配 |
| CN `update_index` 返回真实 added/removed | 单测 set diff |
| stooq 死函数删除 | rg 为零 |
| yf probe/normalize 单点维护 | Plan 2 后三文件委托共享模块 |
| 无表结构/抓取算法变更 | 代码审 + 行为测 |

---

## 9. 明确默认（避免歧义）

| 点 | 选择 |
|----|------|
| D | **真 set diff**，不缩 Protocol 返回值 |
| C `rebase_etf` | **不进** `MarketModule` Protocol |
| A 迁移 | 必做 transform_lists + index_base；其它同义一行可顺手 |
| B | 抽模块，不合并日/周/分钟业务入口 |
| 打包 | Plan 1 完成后再 Plan 2；不并行混提交 |
