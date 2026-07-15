# Code-review Residual Cleanup Plan 1 (A+C+D+E)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 落地 code-review 残留清理的边界债：统一 `or_none`、CLI 收回 market 层、CN `update_index` 真 set diff、删除 db_admin 死代码。

**Architecture:** 纯函数进 `core.http_utils`；CN 适配层诚实返回 ticker 差集；CLI 只编排 `jobs.market_*`，不直调 tushare 采集函数；不改表结构、不改抓取算法。

**Tech Stack:** Python 3.12, pytest, uv, pandas, MariaDB via `core.db_client`（测中 mock）。

**Spec:** `docs/superpowers/specs/2026-07-15-code-review-residual-cleanup-design.md`（§4.1 A, §4.2 C, §4.3 D, §4.4 E）

**Prerequisite:** Plan 1 完成后再做 Plan 2（yfinance 抽取）。

## Global Constraints

- **不做：** 新数据源/新表/新市场、`supports_*`、缩 `MarketModule` 返回值、`rebase_etf` 进 Protocol、改 NAS schema。
- **分层：** `jobs` 不 import 上游 SDK；`main` 对 etf rebase 经 `jobs.market_cn`。
- **测试：** 不连真 NAS；`uv run pytest …`。
- **Commit：** 每 Task 一次 Conventional Commit；`docs/superpowers/` 若 ignore 用 `git add -f`。
- **工作区：** 已有 `apis/tushare/transform_lists.py` 私有 `_or_none` 补丁一并被 Task 2–3 消化。

---

## File Structure

| 文件 | 职责 |
|------|------|
| `modules/db_admin.py` | 删 `get_all_stocks` / `get_tickers_without_prices` |
| `core/http_utils.py` | 新增 `or_none` |
| `apis/tushare/transform_lists.py` | 用 `or_none`；删 `_or_none` |
| `modules/index_base.py` | `register_stocks` 用 `or_none` |
| `apis/tushare/transform_shareholder_return.py` | `_to_str` 内部用 `or_none` |
| `apis/tushare/backfill_lists.py` | 删未使用的 `_to_str` |
| `jobs/market_cn.py` | `update_index` set diff；新增 `rebase_etf` |
| `main.py` | `cmd_rebase` etf 经 market；`cmd_intraday` 经 `_import_market("us")` |
| `tests/test_http_utils.py` | `or_none` 测 |
| `tests/test_transform_lists.py` | ETF NaN 测 |
| `tests/test_market_cn.py` | set diff + rebase_etf |
| `tests/test_cli_rebase_etf.py` | mock market 层 |
| `tests/test_intraday_updater_us.py` | CLI intraday 路径仍绿（可选收紧 mock） |

**不新建业务包。** Plan 2 才新建 `apis/yfinance/probe.py` / `normalize.py`。

---

### Task 1: E — 删除 db_admin 死代码

**Files:**
- Modify: `modules/db_admin.py`
- Test: 全仓 rg + 现有 `tests/test_db_admin.py`

**Interfaces:**
- Consumes: 无
- Produces: `get_all_stocks` / `get_tickers_without_prices` 不存在

- [ ] **Step 1: 确认无引用**

```bash
rg -n "get_all_stocks|get_tickers_without_prices" --type py
```

Expected: 仅 `modules/db_admin.py` 定义处。

- [ ] **Step 2: 删除两函数**

从 `modules/db_admin.py` 删除 `get_all_stocks` 与 `get_tickers_without_prices` 整段（含 docstring）。若因此 `import pymysql.cursors` 仅被这两函数使用，一并删无用 import。

保留：`get_index_tickers`、`create_prices_intraday_table`、`purge_index`、`count_index_rows`、`show_status`。

- [ ] **Step 3: 回归**

```bash
uv run pytest tests/test_db_admin.py -v
rg -n "def get_all_stocks|def get_tickers_without_prices" modules/
```

Expected: pytest PASS；rg 无匹配。

- [ ] **Step 4: Commit**

```bash
git add modules/db_admin.py
git commit -m "chore(db): remove unused stooq-era db_admin helpers"
```

---

### Task 2: A — 添加 `or_none` + 单测（TDD）

**Files:**
- Modify: `core/http_utils.py`
- Modify: `tests/test_http_utils.py`

**Interfaces:**
- Consumes: `pandas as pd`（`http_utils` 已 import）
- Produces: `core.http_utils.or_none(value) -> Any | None`

- [ ] **Step 1: 写失败测**

在 `tests/test_http_utils.py` 增加 import 与测试：

```python
from core.http_utils import (
    fetch_with_retry,
    fetch_urls_sequentially,
    to_float,
    to_int,
    to_date,
    format_cik,
    or_none,
)
import pandas as pd
import math

# ── or_none ───────────────────────────────────────────────────────

def test_or_none_none_and_nan():
    assert or_none(None) is None
    assert or_none(float("nan")) is None
    assert or_none(pd.NA) is None

def test_or_none_passthrough():
    assert or_none("沪深300ETF") == "沪深300ETF"
    assert or_none(0) == 0
    assert or_none("") == ""
```

- [ ] **Step 2: 跑测确认失败**

```bash
uv run pytest tests/test_http_utils.py::test_or_none_none_and_nan tests/test_http_utils.py::test_or_none_passthrough -v
```

Expected: FAIL（`ImportError` 或 `or_none` 未定义）。

- [ ] **Step 3: 实现 `or_none`**

在 `core/http_utils.py` 中 `to_date` **之前**（数据转换区）加入：

```python
def or_none(value):
    """缺失值（None / NaN / NaT / pd.NA）→ None；其余原样返回。

    仅处理标量。调用方勿传入整表。
    """
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value
```

- [ ] **Step 4: 跑测确认通过**

```bash
uv run pytest tests/test_http_utils.py -v
```

Expected: PASS（含原有 to_date/to_float 测）。

- [ ] **Step 5: Commit**

```bash
git add core/http_utils.py tests/test_http_utils.py
git commit -m "feat(core): add http_utils.or_none for NaN-to-None scalars"
```

---

### Task 3: A — 迁移 transform_lists / index_base / shareholder

**Files:**
- Modify: `apis/tushare/transform_lists.py`
- Modify: `modules/index_base.py`
- Modify: `apis/tushare/transform_shareholder_return.py`
- Modify: `apis/tushare/backfill_lists.py`（删死 `_to_str`）
- Modify: `tests/test_transform_lists.py`

**Interfaces:**
- Consumes: `or_none` from Task 2
- Produces: ETF/HK connect 字符串字段 NaN-safe；无私有 `_or_none`

- [ ] **Step 1: 写失败测 — ETF NaN**

在 `tests/test_transform_lists.py` 追加：

```python
def test_transform_etf_basic_nan_fields_become_none():
    import math
    df = pd.DataFrame({
        "ts_code": ["510300.SH"],
        "name": [float("nan")],
        "management": [float("nan")],
        "custodian": [float("nan")],
        "fund_type": [float("nan")],
        "market": [float("nan")],
        "list_date": ["20120528"],
        "issue_date": [None],
        "delist_date": [float("nan")],
        "status": [float("nan")],
    })
    rows = transform_etf_basic(df)
    row = rows[0]
    assert row[0] == "510300.SH"
    assert row[1] is None  # name
    assert row[2] is None  # management
    assert row[3] is None  # custodian
    assert row[4] is None  # fund_type
    assert row[5] is None  # market
    assert row[6] == "2012-05-28"
    assert row[7] is None
    assert row[8] is None  # delist via to_date
    assert row[9] is None  # status
```

可选追加 hk_connect name NaN：

```python
def test_transform_hk_connect_nan_name_becomes_none():
    df = pd.DataFrame({
        "ts_code": ["600519.SH"],
        "name": [float("nan")],
        "in_date": ["20141117"],
        "out_date": [None],
    })
    rows = transform_hk_connect(df, "SH")
    assert rows == [("SH", "600519.SH", None, "2014-11-17", None)]
```

- [ ] **Step 2: 跑测确认失败（若工作区已有私有 _or_none 可能部分通过）**

```bash
uv run pytest tests/test_transform_lists.py::test_transform_etf_basic_nan_fields_become_none -v
```

若工作区 `_or_none` 已让测通过：仍继续 Step 3，把实现换成 canonical。

- [ ] **Step 3: 改 `transform_lists.py`**

```python
"""列表/成分数据转换：…纯函数，零 I/O。"""
from __future__ import annotations

import pandas as pd

from core.http_utils import to_date, or_none


def transform_stocks_a(df: pd.DataFrame) -> pd.DataFrame:
    ...


def transform_stocks_hk(df: pd.DataFrame) -> list[tuple]:
    return [(r["ts_code"], or_none(r["name"]), None, "HKEX") for _, r in df.iterrows()]


def transform_etf_basic(df: pd.DataFrame) -> list[tuple]:
    return [
        (r["ts_code"], or_none(r.get("name")), or_none(r.get("management")), or_none(r.get("custodian")),
         or_none(r.get("fund_type")), or_none(r.get("market")),
         to_date(r.get("list_date")), to_date(r.get("issue_date")),
         to_date(r.get("delist_date")), or_none(r.get("status")))
        for _, r in df.iterrows()
    ]


def transform_hk_connect(df: pd.DataFrame, hs_type: str) -> list[tuple]:
    return [
        (hs_type, r["ts_code"], or_none(r.get("name")),
         to_date(r.get("in_date")), to_date(r.get("out_date")))
        for _, r in df.iterrows()
    ]
```

**删除** 私有 `def _or_none`。

- [ ] **Step 4: 改 `index_base.register_stocks`**

```python
from core.http_utils import or_none  # 文件顶部

def register_stocks(conn, df: pd.DataFrame, exchange: str = None) -> None:
    ...
    rows = []
    for _, r in df.iterrows():
        ticker = r["ticker"]
        name = or_none(r.get("name", None))
        sector = or_none(r.get("sector", None))
        ...
```

删除内嵌 `def _null`。

- [ ] **Step 5: 改 shareholder `_to_str`；删 backfill 死代码**

`apis/tushare/transform_shareholder_return.py`:

```python
from core.http_utils import to_date, to_float, or_none

def _to_str(value) -> str | None:
    v = or_none(value)
    return None if v is None else str(v)
```

`apis/tushare/backfill_lists.py`：删除未使用的 `def _to_str` 整段（rg 确认仅定义无调用）。

- [ ] **Step 6: 跑测**

```bash
uv run pytest tests/test_transform_lists.py tests/test_http_utils.py tests/test_index_base.py tests/test_transform_shareholder_return.py tests/test_backfill_lists.py -v
rg -n "def _or_none" apis/tushare/transform_lists.py
```

Expected: PASS；`_or_none` 无匹配。

- [ ] **Step 7: Commit**

```bash
git add apis/tushare/transform_lists.py modules/index_base.py \
  apis/tushare/transform_shareholder_return.py apis/tushare/backfill_lists.py \
  tests/test_transform_lists.py
git commit -m "refactor: migrate NaN cleaning to core.http_utils.or_none"
```

---

### Task 4: D — CN `update_index` 真 set diff

**Files:**
- Modify: `jobs/market_cn.py`
- Modify: `tests/test_market_cn.py`

**Interfaces:**
- Consumes: `list_active_tickers() -> list[str]`；`backfill_stocks_a() -> int`
- Produces: `update_index() -> tuple[list[str], int, int]` = `(sorted(curr-prev), inserted, len(prev-curr))`

- [ ] **Step 1: 重写失败测**

替换 `tests/test_market_cn.py` 中 `test_update_index_delegates_to_backfill_stocks_a`：

```python
from unittest.mock import patch


@patch("jobs.market_cn.backfill_stocks_a")
@patch("jobs.market_cn.list_active_tickers")
def test_update_index_returns_set_diff(mock_list, mock_backfill):
    """prev/curr ticker sets → added list + removed count; inserted from backfill."""
    from jobs.market_cn import update_index

    mock_list.side_effect = [
        ["600519.SH", "000001.SZ"],           # prev
        ["600519.SH", "000001.SZ", "300750.SZ"],  # curr: +300750
    ]
    mock_backfill.return_value = 1

    new_tickers, inserted, removed = update_index()

    mock_backfill.assert_called_once()
    assert mock_list.call_count == 2
    assert new_tickers == ["300750.SZ"]
    assert inserted == 1
    assert removed == 0


@patch("jobs.market_cn.backfill_stocks_a")
@patch("jobs.market_cn.list_active_tickers")
def test_update_index_removed_count(mock_list, mock_backfill):
    from jobs.market_cn import update_index

    mock_list.side_effect = [
        ["600519.SH", "000001.SZ"],
        ["600519.SH"],  # 000001 gone
    ]
    mock_backfill.return_value = 0

    new_tickers, inserted, removed = update_index()
    assert new_tickers == []
    assert inserted == 0
    assert removed == 1


@patch("jobs.market_cn.backfill_stocks_a")
@patch("jobs.market_cn.list_active_tickers")
def test_update_index_no_change(mock_list, mock_backfill):
    from jobs.market_cn import update_index

    mock_list.side_effect = [
        ["600519.SH"],
        ["600519.SH"],
    ]
    mock_backfill.return_value = 0
    new_tickers, inserted, removed = update_index()
    assert new_tickers == []
    assert removed == 0
```

保留 `test_list_active_tickers` / `test_intraday_is_noop`。

- [ ] **Step 2: 跑测确认失败**

```bash
uv run pytest tests/test_market_cn.py::test_update_index_returns_set_diff -v
```

Expected: FAIL（仍返回 `[]` 或仍 patch `query` count）。

- [ ] **Step 3: 实现 `update_index`**

`jobs/market_cn.py`：

```python
def update_index() -> tuple[list[str], int, int]:
    """更新全量 A 股列表；返回 (added_tickers, backfill_inserted, removed_count)。

    added/removed 基于 stocks 表可见 A 股 ticker 集合前后差（非指数 constituent_changes）。
    新票全量仍依赖空 sync_log + incremental；本函数不单独 backfill 价格。
    """
    prev = set(list_active_tickers())
    inserted = backfill_stocks_a()
    curr = set(list_active_tickers())
    added = sorted(curr - prev)
    removed = len(prev - curr)
    log.info(
        f"[cn] stocks set diff: prev={len(prev)}, curr={len(curr)}, "
        f"+{len(added)} -{removed}, backfill_inserted={inserted}"
    )
    return added, inserted, removed
```

删除 `_A_SHARE_COUNT_SQL` 及对它的使用（若仅被 `update_index` 使用）。`list_active_tickers` 的 SQL 不变。

- [ ] **Step 4: 跑测通过**

```bash
uv run pytest tests/test_market_cn.py -v
```

Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add jobs/market_cn.py tests/test_market_cn.py
git commit -m "fix(cn): update_index returns real ticker set diff"
```

---

### Task 5: C — CLI 旁路收回 market 层

**Files:**
- Modify: `jobs/market_cn.py`
- Modify: `main.py`
- Modify: `tests/test_cli_rebase_etf.py`
- Modify: `tests/test_market_cn.py`（`rebase_etf` 委托测）

**Interfaces:**
- Consumes: `apis.tushare.etf_cn.update_etf_prices(full_rebase: bool) -> int`
- Produces: `jobs.market_cn.rebase_etf(*, full_rebase: bool = True) -> int`  
  **不**加入 `MarketModule` Protocol

- [ ] **Step 1: 写失败测 — market_cn.rebase_etf + CLI**

`tests/test_market_cn.py` 追加：

```python
@patch("apis.tushare.etf_cn.update_etf_prices", return_value=42)
def test_rebase_etf_delegates(mock_upd):
    from jobs.market_cn import rebase_etf
    assert rebase_etf(full_rebase=True) == 42
    mock_upd.assert_called_once_with(full_rebase=True)
```

重写 `tests/test_cli_rebase_etf.py`：

```python
"""rebase --etf-only goes through market_cn, not apis.tushare directly."""
from unittest.mock import patch


@patch("jobs.market_cn.rebase_etf", return_value=100)
def test_rebase_etf_only_calls_market_cn(mock_rebase):
    from main import main
    rc = main(["prices", "rebase", "--market", "cn", "--etf-only"])
    assert rc == 0
    mock_rebase.assert_called_once_with(full_rebase=True)


def test_rebase_etf_only_rejects_non_cn():
    from main import main
    rc = main(["prices", "rebase", "--market", "us", "--etf-only"])
    assert rc == 1
```

注意：`main` 内 `from jobs import market_cn` 或 `_import_market("cn")` 后调 `rebase_etf` 时，patch 目标必须是 **main 实际绑定路径**。若 `cmd_rebase` 使用：

```python
mod = _import_market("cn")
mod.rebase_etf(full_rebase=True)
```

则 patch `jobs.market_cn.rebase_etf` 即可（模块属性）。

- [ ] **Step 2: 跑测确认失败**

```bash
uv run pytest tests/test_cli_rebase_etf.py tests/test_market_cn.py::test_rebase_etf_delegates -v
```

Expected: FAIL（`rebase_etf` 不存在或仍直调 apis）。

- [ ] **Step 3: 实现 `rebase_etf` + 改 main**

`jobs/market_cn.py`：

```python
def rebase_etf(*, full_rebase: bool = True) -> int:
    """行业 ETF index_prices 全量/增量重灌。非 MarketModule；仅 CLI --etf-only。"""
    from apis.tushare.etf_cn import update_etf_prices
    return update_etf_prices(full_rebase=full_rebase)
```

`main.py` `cmd_rebase`：

```python
def cmd_rebase(market: str, codes: list[str] | None, years: int | None, index: str | None, etf_only: bool = False) -> int:
    if etf_only:
        if market != "cn":
            print("--etf-only currently only supports --market cn", file=sys.stderr)
            return 1
        mod = _import_market("cn")
        n = mod.rebase_etf(full_rebase=True)
        print(f"[cn] ETF rebase wrote {n} rows to index_prices")
        return 0
    ...
```

`cmd_intraday`：

```python
def cmd_intraday(interval: str | None, rebase: bool = False) -> int:
    from apis.yfinance.prices_intraday import SUPPORTED_INTERVALS
    mod = _import_market("us")
    intervals = [interval] if interval else None
    log.info(
        f"[intraday] 开始拉取 "
        f"{intervals or SUPPORTED_INTERVALS}"
        + (" (rebase)" if rebase else "")
    )
    result = mod.intraday(intervals=intervals, full_rebase=rebase)
    ok = sum(1 for v in result.values() if v == "ok")
    err = sum(1 for v in result.values() if v.startswith("error"))
    log.info(f"[intraday] 完成: ok={ok}, error={err}")
    return 0
```

- [ ] **Step 4: 跑测**

```bash
uv run pytest tests/test_cli_rebase_etf.py tests/test_market_cn.py \
  tests/test_intraday_updater_us.py::test_cli_intraday_all \
  tests/test_intraday_updater_us.py::test_cli_intraday_single_interval \
  tests/test_intraday_updater_us.py::test_cli_intraday_rebase_flag \
  tests/test_intraday_updater_us.py::test_cli_intraday_no_rebase_flag_default \
  tests/test_market_us_intraday.py -v
rg -n "update_etf_prices" main.py
rg -n "from jobs import market_us" main.py
```

Expected: PASS；`main.py` 无 `update_etf_prices`；无 `from jobs import market_us`（改用 `_import_market`）。

若 CLI intraday 测因 patch 路径碎：patch 改为 `jobs.market_us.intraday` 或保持 `update_intraday`（`market_us.intraday` 内部仍调它——现有 patch 应仍有效）。

- [ ] **Step 5: Commit**

```bash
git add jobs/market_cn.py main.py tests/test_cli_rebase_etf.py tests/test_market_cn.py
git commit -m "refactor(cli): route etf rebase and intraday through market modules"
```

---

### Task 6: Plan 1 总验收

**Files:**
- Modify: `docs/superpowers/specs/2026-07-15-code-review-residual-cleanup-design.md`（状态：Plan 1 已实现 / Plan 2 待做）

- [ ] **Step 1: 全量验收命令**

```bash
uv run pytest tests/test_http_utils.py tests/test_transform_lists.py \
  tests/test_market_cn.py tests/test_cli_rebase_etf.py tests/test_db_admin.py \
  tests/test_cli.py tests/test_index_base.py tests/test_transform_shareholder_return.py \
  tests/test_market_us_intraday.py -v

rg -n "def get_all_stocks|def get_tickers_without_prices" modules/
rg -n "def _or_none" apis/tushare/transform_lists.py
rg -n "update_etf_prices" main.py
```

Expected: 全 PASS；三处 rg 无业务匹配（或仅注释）。

- [ ] **Step 2: 更新 design 状态行**

将 spec 头 `**状态:** 待实现` 改为 `**状态:** Plan 1 已实现；Plan 2 待做`。

- [ ] **Step 3: Commit**

```bash
git add -f docs/superpowers/specs/2026-07-15-code-review-residual-cleanup-design.md
git commit -m "docs: mark residual cleanup Plan 1 done"
```

---

## Plan 1 Self-Review (author)

| Spec 项 | Task |
|---------|------|
| A or_none | Task 2–3 |
| C CLI | Task 5 |
| D set diff | Task 4 |
| E 死代码 | Task 1 |
| 验收 rg/pytest | Task 6 |
| rebase_etf 不进 Protocol | Task 5 明确 |
