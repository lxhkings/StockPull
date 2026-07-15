# Code-review Residual Cleanup Plan 2 (B — yfinance extract)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 yfinance 日/周/分钟线中重复的 AAPL probe、OHLCV normalize、symbol 转换抽到共享模块，三入口行为不变。

**Architecture:** 不合并 `update_prices_batch` / `update_weekly_batch` / `update_intraday` 业务入口。共享：`to_yfinance_us`（已有）、`normalize.py`（frame）、`probe.py`（AAPL readiness）。全部下载仍走 `apis.yfinance.client.download_with_retry`。

**Tech Stack:** Python 3.12, pytest, uv, pandas, yfinance via client wrapper.

**Spec:** `docs/superpowers/specs/2026-07-15-code-review-residual-cleanup-design.md` §4.5 B

**Prerequisite:** Plan 1 已完成并测绿。

## Global Constraints

- **行为契约冻结：** empty → `no_data`；`rate_limit` 仅 except 含 `RateLimit` / `Too Many Requests`；批量 skip 逻辑不改。
- **不做：** 合并日/周/分钟为一个上帝函数；改 batch 大小/delay/表名；给 index prices 加 AAPL probe。
- **分层：** 新模块仅 `apis/yfinance/*` → `core` / `config`；禁止 import `jobs`。
- **测试：** mock `download_with_retry`；不连 Yahoo/NAS。
- **现有测迁移：** 凡 import 私有 `_test_aapl_*` / `_normalize_*` / `_yf_symbol` 的测试，改为测共享模块或保留 thin re-export 过渡一轮后删除。

---

## File Structure

| 文件 | 职责 |
|------|------|
| `apis/yfinance/ticker_utils.py` | 已有 `to_yfinance_us`；三 prices 改用之 |
| **Create** `apis/yfinance/normalize.py` | `normalize_daily_frame` / `normalize_intraday_frame`；共享 MultiIndex/lower |
| **Create** `apis/yfinance/probe.py` | `probe_daily` / `probe_weekly` / `probe_intraday` |
| `apis/yfinance/prices_us.py` | 删私有 probe/normalize/symbol；改 import |
| `apis/yfinance/prices_us_weekly.py` | 同上 |
| `apis/yfinance/prices_intraday.py` | 同上 |
| `apis/yfinance/prices_index.py` | 可选：用 normalize 轻量列 lower（非必须若风险高可跳过） |
| **Create** `tests/test_yf_normalize.py` | normalize 纯函数 |
| **Create** `tests/test_yf_probe.py` | probe status 契约 |
| `tests/test_intraday_probe_rate_limit.py` | patch 目标改 `probe` 或 re-export |
| `tests/test_intraday_updater_us.py` | import 路径更新 |
| `tests/test_stock_updater_us_weekly.py` | 若引用私有 normalize 则更新 |

---

### Task 1: 统一 symbol → `to_yfinance_us`

**Files:**
- Modify: `apis/yfinance/prices_us.py`
- Modify: `apis/yfinance/prices_us_weekly.py`
- Modify: `apis/yfinance/prices_intraday.py`
- Modify: `tests/test_intraday_updater_us.py`（`_yf_symbol` 测）

**Interfaces:**
- Consumes: `apis.yfinance.ticker_utils.to_yfinance_us(ticker: str) -> str`
- Produces: 三文件不再定义 `_yf_symbol`

- [ ] **Step 1: 确认已有 API**

```bash
rg -n "def to_yfinance_us" apis/yfinance/ticker_utils.py
```

Expected: `to_yfinance_us` 存在，语义 `ticker.upper().replace(".", "-")`。

- [ ] **Step 2: 改测 — symbol 测指向 ticker_utils**

`tests/test_intraday_updater_us.py` 中测 `_yf_symbol` 的改为：

```python
def test_to_yfinance_us_dot_to_dash():
    from apis.yfinance.ticker_utils import to_yfinance_us
    assert to_yfinance_us("BRK.B") == "BRK-B"
    assert to_yfinance_us("aapl") == "AAPL"
```

- [ ] **Step 3: 三文件替换**

每个文件顶部：

```python
from apis.yfinance.ticker_utils import to_yfinance_us
```

全文 `_yf_symbol(` → `to_yfinance_us(`，删除 `def _yf_symbol`。

- [ ] **Step 4: 跑相关测**

```bash
uv run pytest tests/test_intraday_updater_us.py tests/test_market_us_intraday.py -v --tb=short
```

Expected: PASS（或仅 normalize 私有名相关失败——若本 Task 未动 normalize 应全绿）。

- [ ] **Step 5: Commit**

```bash
git add apis/yfinance/prices_us.py apis/yfinance/prices_us_weekly.py \
  apis/yfinance/prices_intraday.py tests/test_intraday_updater_us.py
git commit -m "refactor(yf): use ticker_utils.to_yfinance_us everywhere"
```

---

### Task 2: `normalize.py` — 日/周线 frame（TDD）

**Files:**
- Create: `apis/yfinance/normalize.py`
- Create: `tests/test_yf_normalize.py`
- Modify: `apis/yfinance/prices_us.py`
- Modify: `apis/yfinance/prices_us_weekly.py`
- Modify: 引用 `_normalize_yf_frame` / `_normalize_weekly_frame` 的测试

**Interfaces:**
- Produces:
  - `normalize_daily_frame(ticker: str, sub: pd.DataFrame) -> pd.DataFrame`  
    列：`ticker, date, open, high, low, close, volume`；`date` 为 `datetime.date`  
  - （周线与日线同形，**共用同一函数**；不设 `normalize_weekly_frame` 别名除非测需要）

- [ ] **Step 1: 写失败测**

`tests/test_yf_normalize.py`:

```python
import pandas as pd
from datetime import date

from apis.yfinance.normalize import normalize_daily_frame


def test_normalize_daily_empty():
    out = normalize_daily_frame("AAPL", pd.DataFrame())
    assert list(out.columns) == ["ticker", "date", "open", "high", "low", "close", "volume"]
    assert out.empty


def test_normalize_daily_basic_ohlcv():
    sub = pd.DataFrame(
        {
            "Open": [1.0],
            "High": [2.0],
            "Low": [0.5],
            "Close": [1.5],
            "Volume": [100],
        },
        index=pd.DatetimeIndex([pd.Timestamp("2026-07-10")], name="Date"),
    )
    out = normalize_daily_frame("AAPL", sub)
    assert len(out) == 1
    assert out.iloc[0]["ticker"] == "AAPL"
    assert out.iloc[0]["date"] == date(2026, 7, 10)
    assert float(out.iloc[0]["close"]) == 1.5
```

可从 `tests/test_stock_updater_us_weekly.py` 的 normalize 测搬一例到此文件。

- [ ] **Step 2: 跑测失败**

```bash
uv run pytest tests/test_yf_normalize.py -v
```

Expected: FAIL import。

- [ ] **Step 3: 实现 `normalize_daily_frame`**

从 `prices_us._normalize_yf_frame` **原样迁入** `apis/yfinance/normalize.py`：

```python
"""yfinance DataFrame → 标准 OHLCV 列。纯转换，零 I/O。"""
from __future__ import annotations

import pandas as pd


def normalize_daily_frame(ticker: str, sub: pd.DataFrame) -> pd.DataFrame:
    """单 ticker 子表 → [ticker, date, open, high, low, close, volume]。"""
    cols = ["ticker", "date", "open", "high", "low", "close", "volume"]
    if sub is None or sub.empty:
        return pd.DataFrame(columns=cols)

    df = sub.reset_index()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df.columns = [str(c).lower() for c in df.columns]
    if "date" not in df.columns:
        for cand in ("datetime", "index"):
            if cand in df.columns:
                df = df.rename(columns={cand: "date"})
                break

    df["date"] = pd.to_datetime(df["date"]).dt.date
    df["ticker"] = ticker
    df = df.dropna(subset=["date", "close"])
    df = df[cols].sort_values("date").reset_index(drop=True)
    return df
```

- [ ] **Step 4: prices_us / weekly 改用**

```python
from apis.yfinance.normalize import normalize_daily_frame
```

- 所有 `_normalize_yf_frame(...)` → `normalize_daily_frame(...)`
- 所有 `_normalize_weekly_frame(...)` → `normalize_daily_frame(...)`
- 删除两文件内私有 normalize 定义

- [ ] **Step 5: 更新旧测 import**

若 `tests/test_stock_updater_us_weekly.py` 有：

```python
from apis.yfinance.prices_us_weekly import _normalize_weekly_frame
```

改为：

```python
from apis.yfinance.normalize import normalize_daily_frame as _normalize_weekly_frame
# 或直接改断言调用 normalize_daily_frame
```

- [ ] **Step 6: 跑测**

```bash
uv run pytest tests/test_yf_normalize.py tests/test_stock_updater_us_weekly.py -v --tb=short
```

Expected: PASS。

- [ ] **Step 7: Commit**

```bash
git add apis/yfinance/normalize.py apis/yfinance/prices_us.py \
  apis/yfinance/prices_us_weekly.py tests/test_yf_normalize.py \
  tests/test_stock_updater_us_weekly.py
git commit -m "refactor(yf): extract normalize_daily_frame for US daily/weekly"
```

---

### Task 3: `normalize_intraday_frame`

**Files:**
- Modify: `apis/yfinance/normalize.py`
- Modify: `apis/yfinance/prices_intraday.py`
- Modify: `tests/test_yf_normalize.py`
- Modify: `tests/test_intraday_updater_us.py`

**Interfaces:**
- Produces: `normalize_intraday_frame(ticker: str, interval: str, sub: pd.DataFrame) -> pd.DataFrame`  
  列：`ticker, interval, datetime, open, high, low, close, volume`；datetime 无时区（UTC 剥除，与现网一致）

- [ ] **Step 1: 写失败测**

从 `tests/test_intraday_updater_us.py` 的 `_normalize_frame` 测复制逻辑到 `test_yf_normalize.py`，import `normalize_intraday_frame`。

- [ ] **Step 2: 实现**

把 `prices_intraday._normalize_frame` **原样**迁到 `normalize.py`，改名为 `normalize_intraday_frame`。

- [ ] **Step 3: prices_intraday 改用并删私有函数**

- [ ] **Step 4: 更新 `test_intraday_updater_us.py` import**

```python
from apis.yfinance.normalize import normalize_intraday_frame as _normalize_frame
```

或改测试直接用新名。

- [ ] **Step 5: 跑测**

```bash
uv run pytest tests/test_yf_normalize.py tests/test_intraday_updater_us.py -v --tb=short
```

Expected: PASS。

- [ ] **Step 6: Commit**

```bash
git add apis/yfinance/normalize.py apis/yfinance/prices_intraday.py \
  tests/test_yf_normalize.py tests/test_intraday_updater_us.py
git commit -m "refactor(yf): extract normalize_intraday_frame"
```

---

### Task 4: `probe.py` — 三 probe（TDD）

**Files:**
- Create: `apis/yfinance/probe.py`
- Create: `tests/test_yf_probe.py`
- Modify: `apis/yfinance/prices_us.py`
- Modify: `apis/yfinance/prices_us_weekly.py`
- Modify: `apis/yfinance/prices_intraday.py`
- Modify: `tests/test_intraday_probe_rate_limit.py`
- Modify: 所有 patch `*_test_aapl_*` 的测试

**Interfaces:**
- Produces:
  - `probe_daily(target_date: date) -> tuple[Optional[pd.DataFrame], str]`
  - `probe_weekly(target_monday: date) -> tuple[Optional[pd.DataFrame], str]`
  - `probe_intraday(interval: str) -> tuple[Optional[date], str]`
- Status 集合：`ok` | `no_data` | `rate_limit` | `error`（与现网一致）

- [ ] **Step 1: 写失败测（契约金丝雀）**

`tests/test_yf_probe.py`：

```python
from datetime import date
from unittest.mock import patch

import pandas as pd


@patch("apis.yfinance.probe.download_with_retry")
def test_probe_intraday_rate_limit(mock_dl):
    from apis.yfinance.probe import probe_intraday
    mock_dl.side_effect = Exception("Too Many Requests")
    latest, status = probe_intraday("1h")
    assert latest is None
    assert status == "rate_limit"


@patch("apis.yfinance.probe.download_with_retry")
def test_probe_intraday_empty_is_no_data(mock_dl):
    from apis.yfinance.probe import probe_intraday
    mock_dl.return_value = pd.DataFrame()
    latest, status = probe_intraday("1h")
    assert latest is None
    assert status == "no_data"


@patch("apis.yfinance.probe.download_with_retry")
def test_probe_daily_rate_limit(mock_dl):
    from apis.yfinance.probe import probe_daily
    mock_dl.side_effect = Exception("RateLimit")
    df, status = probe_daily(date(2026, 7, 10))
    assert df is None
    assert status == "rate_limit"
```

把 `tests/test_intraday_probe_rate_limit.py` 的 import/patch 从  
`apis.yfinance.prices_intraday._test_aapl_intraday`  
改为  
`apis.yfinance.probe.probe_intraday`  
（或 prices_intraday 保留别名 `_test_aapl_intraday = probe_intraday` 过渡——**优先直接改测与调用点，不留别名**）。

- [ ] **Step 2: 跑测失败**

```bash
uv run pytest tests/test_yf_probe.py -v
```

Expected: FAIL import。

- [ ] **Step 3: 实现 `probe.py`**

将下列函数 **原样搬迁**（仅改名 + 集中 logging）：

| 源 | 目标 |
|----|------|
| `prices_us._test_aapl_data` | `probe_daily` |
| `prices_us_weekly._test_aapl_weekly` | `probe_weekly` |
| `prices_intraday._test_aapl_intraday` | `probe_intraday` |

`probe.py` 骨架：

```python
"""AAPL readiness probes for yfinance US feeds. Status: ok|no_data|rate_limit|error."""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Optional

import pandas as pd

from apis.yfinance.client import download_with_retry
# 分钟线 lookback / interval map：从 prices_intraday 已有常量 import，
# 或把 INTERVAL_LOOKBACK_DAYS / YF_INTERVAL_MAP 提到 probe 旁常量；
# 禁止循环 import —— 若 prices_intraday 已 import probe，则 lookback 常量放 probe 或独立 constants。

log = logging.getLogger(__name__)
```

**循环 import 处理（强制）:**

- `INTERVAL_LOOKBACK_DAYS`、`YF_INTERVAL_MAP`、`YF_TIMEOUT` 若只在 probe+intraday 用：  
  - 方案 A（推荐）：常量留在 `prices_intraday.py`，`probe_intraday` 接受 lookback 参数；或  
  - 方案 B：小 dict 复制进 `probe.py`（与现网数值一致）；或  
  - 方案 C：新建 `apis/yfinance/intraday_constants.py` 两边 import。

选 **B 或 C**；禁止 `probe` ↔ `prices_intraday` 互 import。

`probe_daily` / `probe_weekly` 仅依赖 `download_with_retry` + `last_us_trading` 的调用方传入 `target_date`（probe 自身不调 trading_calendar 除非源码已调——**保持源码依赖**）。

- [ ] **Step 4: 三 prices 文件改调用**

```python
from apis.yfinance.probe import probe_daily  # us
# _test_aapl_data(...) → probe_daily(...)
```

```python
from apis.yfinance.probe import probe_weekly
```

```python
from apis.yfinance.probe import probe_intraday
# update_intraday 内 _test_aapl_intraday → probe_intraday
```

删除三处私有 `_test_aapl_*`。

- [ ] **Step 5: 批量入口 rate_limit 测**

`test_intraday_probe_rate_limit.py` 中：

```python
@patch("apis.yfinance.prices_intraday.probe_intraday")  # 若 from probe import 到 prices 命名空间
# 或
@patch("apis.yfinance.probe.probe_intraday")
```

以 **prices_intraday 模块内绑定名** 为准：若写 `from apis.yfinance.probe import probe_intraday`，patch `apis.yfinance.prices_intraday.probe_intraday`。

- [ ] **Step 6: 跑测**

```bash
uv run pytest tests/test_yf_probe.py tests/test_intraday_probe_rate_limit.py \
  tests/test_intraday_updater_us.py tests/test_stock_updater_us_weekly.py -v --tb=short
```

Expected: PASS。

- [ ] **Step 7: 确认私有函数消失**

```bash
rg -n "def _test_aapl|def _normalize_yf_frame|def _normalize_weekly_frame|def _normalize_frame|def _yf_symbol" apis/yfinance/
```

Expected: 无匹配（或仅注释）。

- [ ] **Step 8: Commit**

```bash
git add apis/yfinance/probe.py apis/yfinance/prices_us.py \
  apis/yfinance/prices_us_weekly.py apis/yfinance/prices_intraday.py \
  tests/test_yf_probe.py tests/test_intraday_probe_rate_limit.py \
  tests/test_intraday_updater_us.py
git commit -m "refactor(yf): extract AAPL probes into apis.yfinance.probe"
```

---

### Task 5: prices_index 轻量 normalize（可选但推荐）

**Files:**
- Modify: `apis/yfinance/normalize.py`（可选 `lower_columns(df)` helper）
- Modify: `apis/yfinance/prices_index.py`
- Modify: `tests/test_us_index_price.py`（行为金丝雀，应仍绿）

**Interfaces:**
- 若抽取成本 > 收益：本 Task 可 **SKIP** 并在 commit message 注明；Plan 2 仍算完成（spec 写「尽量」）。

- [ ] **Step 1: 评估**

`prices_index` 当前：

```python
df = df.reset_index()
df.columns = [str(c).lower() if not isinstance(c, tuple) else str(c[0]).lower() for c in df.columns]
```

若与 daily 不完全同构，**不要硬套** `normalize_daily_frame`（index 无 ticker 列、只要 close）。可加：

```python
def lower_ohlc_columns(df: pd.DataFrame) -> pd.DataFrame:
    ...
```

- [ ] **Step 2: 改或跳过**

- 改：用 helper 后 `uv run pytest tests/test_us_index_price.py -v`  
- 跳过：直接进入 Task 6

- [ ] **Step 3: Commit（若改了）**

```bash
git commit -m "refactor(yf): reuse column lower helper in prices_index"
```

---

### Task 6: Plan 2 总验收 + 关 design

**Files:**
- Modify: `docs/superpowers/specs/2026-07-15-code-review-residual-cleanup-design.md` → 状态「已实现」

- [ ] **Step 1: 验收命令**

```bash
uv run pytest tests/test_yf_normalize.py tests/test_yf_probe.py \
  tests/test_intraday_probe_rate_limit.py tests/test_intraday_updater_us.py \
  tests/test_stock_updater_us_weekly.py tests/test_us_index_price.py \
  tests/test_market_us_intraday.py -v

rg -n "def _test_aapl|def _normalize_yf_frame|def _normalize_weekly_frame|def _yf_symbol" apis/yfinance/
```

Expected: PASS；rg 无私有三副本。

- [ ] **Step 2: 更新 design 状态为「已实现」**

- [ ] **Step 3: Commit**

```bash
git add -f docs/superpowers/specs/2026-07-15-code-review-residual-cleanup-design.md
git commit -m "docs: mark code-review residual cleanup fully implemented"
```

---

## Plan 2 Self-Review (author)

| Spec 项 | Task |
|---------|------|
| 统一 symbol | Task 1（复用 `to_yfinance_us`，不新建） |
| normalize 日/周 | Task 2 |
| normalize 分钟 | Task 3 |
| probe 三入口 | Task 4 |
| prices_index 尽量 | Task 5 optional |
| 行为契约 rate_limit/no_data | Task 4 金丝雀 + 现有测 |
| 不合并业务入口 | 全 plan 未合并 update_* |
| 循环 import | Task 4 强制 B/C 常量策略 |
