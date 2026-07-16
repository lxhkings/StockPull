# Code-review Probe Cleanup — 设计文档

**日期:** 2026-07-16  
**状态:** 已实现  
**范围:** 上一轮 `/code-review` 对 residual cleanup 的残留项 P0+P1+P2  
**非目标:** 不合并 `prices_us` / `prices_us_weekly` batch 编排（P3）  
**来源:** `/code-review` 严格审查 + brainstorming  
**前置:** `docs/superpowers/specs/2026-07-15-code-review-residual-cleanup-design.md`（已实现）

**工作流:**

1. 本文件 = design spec  
2. implementation plan: `docs/superpowers/plans/2026-07-16-code-review-probe-cleanup.md`  
3. 再实现  

**用户锁定:**

| # | 项 | 决策 |
|---|-----|------|
| 范围 | P0+P1+P2 | 审查项全收，**不含**日/周 batch 合并 |
| 做法 | 方案 A | 契约收紧（status-only）+ 外科手术；不保留假 DF 返回值 |
| timeout | probe daily/weekly | 统一 `YF_TIMEOUT`（现写死 30 → config 60） |

---

## 1. 背景

Residual cleanup Plan 2 已抽出 `apis/yfinance/probe.py` / `normalize.py`，但 probe **日/周函数仍近同构**，且：

- 手写 MultiIndex 降列，未复用 `lower_ohlc_columns`
- 限速字符串判定复制 3 次
- `probe_daily` / `probe_weekly` 返回 `(DataFrame|None, status)`，生产路径丢弃 DF；`prices_us` 仍有死变量 `test_df`
- 另有：纯 NaN 清洗散落、`update_index_price` 与 `rebase_etf` 双委托、过时模块头、`http_utils` 空行

目标：**抓取/写表/batch skip 语义不变**，删掉假契约与重复块。

---

## 2. 非目标

- 不合并日线/周线 `update_*_batch` 编排  
- 不改表结构、batch 大小、delay、sync data_type  
- 不把 `or_none` 塞进 `float(...)` / `to_float` / `to_date` 路径  
- 不改 `MarketModule` Protocol  
- 不开放 CN/HK 分钟线  

---

## 3. 分层

```
apis/yfinance/probe.py     ← P0 主改
apis/yfinance/normalize.py ← 只被 probe 复用 lower_ohlc_columns（不改 API）
apis/yfinance/prices_us.py / prices_us_weekly.py / prices_intraday.py  ← 调用契约 + docstring
jobs/market_cn.py          ← P1 委托
core/http_utils.py         ← P2 空行
apis/static/russell_ishares.py, apis/futu/*  ← P1 or_none
tests/*                    ← 同步签名
```

---

## 4. 设计分项

### 4.1 P0 — probe 收敛

**公开契约：**

```python
def probe_daily(target_date: date) -> str
def probe_weekly(target_monday: date) -> str
# "ok" | "no_data" | "rate_limit" | "error"

def probe_intraday(interval: str) -> tuple[Optional[date], str]
# 不变
```

**内部：**

- `_is_rate_limit(exc) -> bool`：消息含 `RateLimit` 或 `Too Many Requests`
- `_probe_has_date(*, interval, start, end, target, context) -> str`：download → empty/`lower_ohlc_columns` → date 列 → 命中目标日
- daily/weekly：算窗口后调 `_probe_has_date`
- intraday：保留 latest_date 逻辑；except 走 `_is_rate_limit`；`timeout=YF_TIMEOUT`
- daily/weekly `timeout`：现 `30` → **`YF_TIMEOUT`**

**调用方：**

```python
status = probe_daily(last_trading)       # prices_us；删 test_df
status = probe_weekly(target_monday)     # prices_us_weekly
```

batch 对 status 的映射保持：`rate_limit` → `error: rate_limit`，`no_data` → `error: no_data`，`error` → `error: test_failed`。

### 4.2 P1 — or_none + market_cn 委托

| 位置 | 动作 |
|------|------|
| `russell_ishares` 列清洗 | `or_none(v)` |
| `futu/snapshot_daily._num` | 用 `or_none` |
| `futu/backfill_earnings` `_date_part` / payload | `or_none` |
| `transform_financial` / `transform_valuation` | **不动** |
| `transform_shareholder_return` 行门槛 `pd.isna` | **不动** |

```python
def update_index_price() -> int:
    return rebase_etf(full_rebase=False)
```

`rebase_etf` 仍是唯一 `from apis.tushare.etf_cn import update_etf_prices` 的 market 入口。

### 4.3 P2 — 整洁

- 三 prices 模块 docstring：去掉 `stock_updater_*` / `data/` 旧路径，写真实职责  
- `http_utils.or_none` 后多余空行删除  
- 不扩 README（除非错误内部引用；预期无）

---

## 5. 测试

- `test_yf_probe`：status-only；补目标日 hit / miss  
- weekly batch 测：`return_value="rate_limit"` 等  
- `test_market_cn_etf_hook`：`assert_called_once_with(full_rebase=False)`  
- intraday 测形状不变  

验收命令见 plan。

---

## 6. 成功标准

| 标准 | 验证 |
|------|------|
| 日/周 probe 返回 `str` | 签名 + 调用点无 DF 解包 |
| 无 `test_df` | `rg test_df apis/yfinance/prices_us.py` → 0 |
| 无 probe `timeout=30` | `rg` → 0 |
| 降列/限速单点 | 读 `probe.py` |
| ETF daily 经 `rebase_etf` | `update_index_price` 委托 |
| 无 batch 合并 | diff 不含编排合并 |
| 相关 pytest 绿 | plan 命令 |

---

## 7. 风险

| 风险 | 缓解 |
|------|------|
| timeout 30→60 略改等待 | 只影响 probe 等待上限；status 逻辑不变；单测 mock 无感 |
| mock 返回元组残留 | plan 显式改 weekly 测与 yf_probe |
| `update_index_price` 调用带 `full_rebase=False` | 更新 etf_hook 断言 |
