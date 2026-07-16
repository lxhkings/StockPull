# Code-review 结构债收口（P0–P2）— 设计文档

**日期:** 2026-07-16  
**状态:** 已批准（brainstorming §1–§2，方案 A）  
**范围:** 上轮 `/code-review` 对 structural debt cleanup 的 P0–P2 修复项  
**来源:** code-review 严格审查 + brainstorming  
**前置:** `docs/superpowers/specs/2026-07-16-structural-debt-cleanup-design.md`（已实现）

**工作流:**

1. 本文件 = design spec  
2. implementation plan（`writing-plans`）  
3. 再实现  

**用户锁定:**

| # | 项 | 决策 |
|---|-----|------|
| 方案 | A 外科手术 | 按 review 表全收 P0–P2 |
| 非目标 | 方案 B 重写 start 状态机 | 不做 |
| 入口 | `update_prices_batch` / `update_weekly_batch` | 签名与 jobs 调用面不变 |
| 日/周 | CLI/作业仍分开 | 不合并采集 |

---

## 1. 背景

结构债清理 P0–P4 已合入 `main`。严格 code-review 认定方向正确，但共享路径仍有：

- US runner 三份同构 `chunked → download → sleep`
- 「全部已同步」日志挂在错误 `else`
- CN `_save_weekly_prices_batch` 生产死码 + 假契约测
- US weekly 测名实不符
- CN 热路径每 ticker `get_client()`；normalize 后重复 `to_float`；日志与真实 start 不一致
- `UsPriceSpec.end_exclusive` Callable 可收成标量

本轮只收口这些项，不扩功能。

---

## 2. 目标

1. 修正误导日志与测试债务，删除生产死代码。  
2. US batch 编排循环只保留一处。  
3. CN client 提升到 run 级；去掉重复标量转换；log 真实 start。  
4. `end_exclusive` → `end_pad_days`，Spec 更直。  

**行为不变：** 抓取窗口、写表语义、probe 早退、日/周 CLI 分离。

---

## 3. 非目标

- 不重写 CN new/pending 双轨为统一 start 解析器  
- 不跨源 PriceEngine、不改 YF/Tushare 限速与 batch 大小  
- 不动 futu / CLI argv / jobs 签名  
- 不强制 daily 也抽 `build_us_daily_spec`（仅 weekly 为硬要求）  

---

## 4. 分项设计

### 4.1 P0a — US「全部已同步」日志

**文件:** `apis/yfinance/prices_batch.py`

在 new/pending 处理之后：

```text
if not new_tickers and not pending_tickers:
    log.info(...全部已同步到 {target})
```

删除挂在 `if pending_tickers` 上的 `else` 日志。rebase 路径不打这句。

### 4.2 P0b — weekly 契约测

**文件:** `apis/yfinance/prices_us_weekly.py`，`tests/test_stock_updater_us_weekly.py`

**推荐：** 抽 `build_us_weekly_spec() -> UsPriceSpec`；`update_weekly_batch` 调用它。

测试断言：

- `price_table == "prices_weekly"`
- `data_type == "price_weekly"`
- `interval == "1wk"`
- `on_duplicate is False`
- `end_pad_days == 7`（P2a 落地后）

删除或改写名实不符的 `test_weekly_spec_targets_prices_weekly_table`（不得仅断言 `[] → {}`）。  
空列表行为由既有 empty 测覆盖。

### 4.3 P0c — 删 CN 死 helper

**文件:** `apis/tushare/prices_cn_weekly.py`，相关 tests

删除 `_save_weekly_prices_batch` 及「供单测保留」文档。  
删除 `test_save_weekly_prices_batch_uses_prices_weekly_table`。  
真路径契约由 `test_cn_prices_batch` 的 flush `price_table=` 或对 `CnPriceSpec` 的断言覆盖。  
可保留 `_normalize_pro_bar` re-export 若现有 normalize 测依赖。

### 4.4 P1a — `_run_ticker_batches`

**文件:** `apis/yfinance/prices_batch.py`

```python
def _run_ticker_batches(conn, tickers, start_date, result, *, spec, years=None):
    if not tickers:
        return
    batches = list(chunked(tickers, YF_BATCH_SIZE))
    for i, batch in enumerate(batches, 1):
        _download_and_save(conn, batch, start_date, result, spec=spec, years=years)
        if i < len(batches):
            _sleep_between_batches(spec.label)
```

rebase / new / pending 三处改为各调一次。  
**验收:** 该文件内仅此一处 `chunked(..., YF_BATCH_SIZE)` 编排循环。

### 4.5 P1b — CN `get_client` 一次

**文件:** `apis/tushare/prices_cn_batch.py`

- `run_cn_equity_batch` 开头 `client = get_client()`
- `_fetch_one(client, ticker, start, end, freq)`
- `_process_tickers_batched` 传入 client  

测试 patch `apis.tushare.prices_cn_batch.get_client` 保持有效。

### 4.6 P2a — `end_pad_days`

**文件:** `prices_batch.py`，`prices_us.py`，`prices_us_weekly.py`，`test_yf_prices_batch.py`

`UsPriceSpec`：删除 `end_exclusive: Callable[[date], date]`；新增 `end_pad_days: int`。  
`_download_and_save`：`end_dt = target + timedelta(days=spec.end_pad_days)`。  
daily `end_pad_days=1`；weekly `end_pad_days=7`。  
`probe` / `target_date` 仍为 Callable。

### 4.7 P2b — 去掉重复 to_float

**文件:** `prices_cn_batch.py`

`normalize_pro_bar` 已转换后，组 price row 直接用列值，不再二次 `to_float`/`to_int`（类型与 normalize 输出一致即可）。

### 4.8 P2c — 日志真 start

**文件:** `prices_cn_batch.py`

new/回填日志打印实际 start 字符串（`TUSHARE_BACKFILL_START` 或 years 推算结果），不把「HISTORY_YEARS_CN 年」写成与 start 不符的口号。  
可选：注释说明 `full_rebase` 在 new vs pending 中的含义。  
**不**合并 new/pending 双轨。

---

## 5. 测试与提交

**聚焦测:**

```bash
uv run pytest tests/test_yf_prices_batch.py tests/test_stock_updater_us_weekly.py \
  tests/test_stock_updater_cn_weekly.py tests/test_cn_prices_batch.py -q
uv run pytest tests/ -q
```

**结构检查:**

```bash
rg -n '_save_weekly_prices_batch' --type py   # 无命中
rg -n 'chunked\(' apis/yfinance/prices_batch.py  # 编排循环一处
```

**建议 commit 切分:**

1. `fix(yf/cn): review P0 — sync log, real weekly/cn contracts, drop dead helper`  
2. `refactor(yf/cn): review P1–P2 — batch loop, client hoist, end_pad_days, row clean`

---

## 6. 风险

| 项 | 风险 | 缓解 |
|----|------|------|
| Spec 字段改名 | 测构造漏改 | 全量 pytest；grep `end_exclusive` |
| client 注入 | mock 路径 | 现有 batch 测 patch 点 |
| 去 to_float | 类型边缘 | normalize 测 + cn batch 测 |

---

## 7. 验收清单（完成定义）

- [ ] P0a–c、P1a–b、P2a–c 全部落地  
- [ ] 无 `_save_weekly_prices_batch`  
- [ ] weekly Spec 测真断言表/类型/interval  
- [ ] `prices_batch` 单处 batch 循环  
- [ ] `pytest tests/` 全绿  
- [ ] 日/周 public 入口与 CLI 分离不变  
