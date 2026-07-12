# Code-review 残留债收口 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 落实 code-review closure design：daily 与 intraday 拆开、HK weekly no-op、三处 probe 限速语义对齐、purge 事务、CLI 死代码收口、prices_index 写路径测与文档归档。

**Architecture:** 外科改动、不加新抽象。`Pipeline.daily` 只编排日线；`intraday` 仍在 Protocol + `prices intraday` CLI。未实现能力统一 `return {}`。Probe 限速只认 exception 字符串。`purge_index` 单连接 commit/rollback。

**Tech Stack:** Python 3.12, pytest, uv, MariaDB client via `core.db_client`.

**Spec:** `docs/superpowers/specs/2026-07-12-code-review-closure-design.md`

## Global Constraints

- **不做：** 港股周线实现、`supports_*`、`daily --with-intraday`、增强 `download_with_retry` 日志捕获、通用 `transaction()` helper、改表结构。
- **分层：** `jobs` 不 import SDK；`modules` 不 import `jobs`/`apis`。
- **测试：** 不连真 NAS；mock DB / yfinance。
- 命令：`uv run pytest …`（项目用 uv）。
- 每 Task 独立 commit；Conventional Commits（中英均可，说明行为）。
- 实现后把 design 状态改为「已实现」仅在最后 Task。

---

## File Structure

| 文件 | 职责 |
|------|------|
| `jobs/pipeline.py` | daily 去掉 Step 4 intraday；docstring |
| `jobs/market_hk.py` | `weekly` → `return {}` |
| `apis/yfinance/prices_intraday.py` | probe `rate_limit` + `update_intraday` skip |
| `apis/yfinance/prices_us.py` | probe docstring 对齐（代码分支已有） |
| `apis/yfinance/prices_us_weekly.py` | probe docstring 对齐（代码分支已有） |
| `modules/db_admin.py` | `purge_index` 单连接事务 |
| `main.py` | `_format_run_result`；删 `cmd_tushare_sync` |
| `tests/test_pipeline.py` | daily 不调 intraday |
| `tests/test_pipeline_intraday.py` | 改写为 skips_intraday |
| `tests/test_market_hk.py` | weekly no-op |
| `tests/test_intraday_probe_rate_limit.py`（新建）或扩现有 | probe + batch rate_limit |
| `tests/test_db_admin.py` | purge commit/rollback |
| `tests/test_main_tushare_backfill.py` | sync 经 CLI → backfill |
| `tests/test_us_index_price.py` | 写路径 mock |
| `CLAUDE.md` / `README.md` | Pipeline 步骤与 protocol 文案 |
| `docs/SPEC_code_review_followup.md` | 归档头 |
| `docs/superpowers/specs/2026-07-12-code-review-closure-design.md` | 状态 → 已实现 |

**不新建业务模块。** 可选新建 `tests/test_intraday_probe_rate_limit.py` 专测 probe；也可塞进 `tests/test_intraday_updater_us.py`——本 plan 用**新建小文件**避免大文件纠缠。

---

### Task 1: Pipeline.daily 不再调用 intraday

**Files:**
- Modify: `jobs/pipeline.py`
- Modify: `tests/test_pipeline.py`
- Modify: `tests/test_pipeline_intraday.py`
- Modify: `CLAUDE.md`（Pipeline flow 列表）
- Modify: `README.md`（MarketModule 列表中 daily/intraday 描述）

**Interfaces:**
- Consumes: `MarketModule` 仍含 `intraday(...)`（本 Task 不删）
- Produces: `Pipeline.daily(index=None) -> None` 仅调用 `update_index` / `list_active_tickers` / `incremental` / `update_index_price`

- [ ] **Step 1: 改失败测 — daily 不调用 intraday**

重写 `tests/test_pipeline_intraday.py`：

```python
"""Tests for Pipeline.daily() — intraday is CLI-only, not part of daily."""
from unittest.mock import MagicMock

from jobs.pipeline import Pipeline


def _full_mod(**overrides):
    mod = MagicMock()
    mod.market_id = "us"
    mod.update_index.return_value = ([], 0, 0)
    mod.list_active_tickers.return_value = []
    mod.incremental.return_value = {}
    mod.update_index_price.return_value = 0
    mod.intraday.return_value = {}
    for k, v in overrides.items():
        setattr(mod, k, v)
    return mod


def test_pipeline_daily_does_not_call_intraday():
    mod = _full_mod()
    Pipeline(mod).daily()
    mod.intraday.assert_not_called()


def test_pipeline_daily_cn_still_completes_without_intraday():
    mod = _full_mod(market_id="cn")
    Pipeline(mod).daily()
    mod.update_index_price.assert_called_once()
    mod.intraday.assert_not_called()
```

改 `tests/test_pipeline.py` 中 `test_pipeline_runs_steps_in_order`：

```python
def test_pipeline_runs_steps_in_order():
    """Pipeline: update_index → incremental → update_index_price (no intraday)."""
    from jobs.pipeline import Pipeline

    market_module = MagicMock()
    market_module.market_id = "us"
    market_module.update_index.return_value = (["NEW1", "NEW2"], 5, 1)
    market_module.list_active_tickers.return_value = ["AAPL", "MSFT", "NEW1", "NEW2"]
    market_module.incremental.return_value = {
        "AAPL": "ok", "MSFT": "ok", "NEW1": "ok", "NEW2": "ok",
    }
    market_module.update_index_price.return_value = 1
    market_module.intraday.return_value = {}

    p = Pipeline(market_module)
    p.daily()

    market_module.update_index.assert_called_once()
    market_module.incremental.assert_called_once_with(["AAPL", "MSFT", "NEW1", "NEW2"])
    market_module.update_index_price.assert_called_once()
    market_module.intraday.assert_not_called()
```

其余 `test_pipeline.py` 用例若仍 `assert_called` intraday，一律改为 `assert_not_called` 或删掉对 intraday 的设置依赖（可保留 `return_value` 无妨）。

- [ ] **Step 2: 跑测确认失败**

```bash
uv run pytest tests/test_pipeline_intraday.py tests/test_pipeline.py -v
```

Expected: FAIL — `intraday` 仍被调用（`assert_not_called` 失败）。

- [ ] **Step 3: 改 `jobs/pipeline.py`**

模块 docstring 改为（要点）：

```python
"""Generic per-market pipeline orchestrator.

A market module must expose MarketModule (see Protocol below).
CN/HK: list_active_tickers ignores index; intraday/weekly may no-op.
US: index filters SP500/RUSSELL1000; intraday is CLI-only (not in daily).

Price path: single incremental() — new tickers have empty sync_log so
updaters already full-history pull; no separate backfill_new step.
"""
```

`daily()` 删除 Step 4 整段：

```python
        log.info(f"[{mid}] === Step 4: intraday update ===")
        self.m.intraday()
```

在 `update_index_price` 日志后直接：

```python
        log.info(f"[{mid}] === pipeline complete ===")
```

Protocol **保留** `intraday` 方法签名不动。

- [ ] **Step 4: 文档对齐**

`CLAUDE.md` Pipeline flow：

```markdown
**Pipeline flow** (`jobs/pipeline.py`):
1. `update_index()` — snapshot index constituents, detect added/removed
2. `incremental()` — day prices (new tickers full-history via empty sync_log)
3. `update_index_price()` — index/ETF daily close
4. `weekly()` / `rebase()` / `intraday()` — **separate CLI**, not in daily
   - `prices weekly` / `prices rebase` / `prices intraday`
```

`README.md` 中类似：

- 删/改「daily 始终调用」intraday  
- `weekly`：HK 改为 no-op（可与 Task 2 一并改 README 一句，本 Task 至少改 daily/intraday）  
- 分钟线段已写 `prices intraday` 独立命令则保留，补一句：**不包含在 `prices daily` 内**

- [ ] **Step 5: 跑测通过**

```bash
uv run pytest tests/test_pipeline_intraday.py tests/test_pipeline.py tests/test_market_us_intraday.py -v
```

Expected: PASS（CLI/market_us intraday 默认仍 15m+1h）。

- [ ] **Step 6: Commit**

```bash
git add jobs/pipeline.py tests/test_pipeline.py tests/test_pipeline_intraday.py CLAUDE.md README.md
git commit -m "$(cat <<'EOF'
fix(pipeline): daily no longer runs intraday

Intraday is CLI-only (prices intraday); keeps Protocol method for US/CN/HK.
EOF
)"
```

---

### Task 2: HK weekly → no-op

**Files:**
- Modify: `jobs/market_hk.py`
- Modify: `tests/test_market_hk.py`
- Modify: `README.md`（若仍写 HK `NotImplementedError`）

**Interfaces:**
- Produces: `market_hk.weekly(tickers: list[str] | None = None) -> dict[str, str]` 恒返回 `{}`

- [ ] **Step 1: 改测试**

替换 `test_weekly_not_implemented`：

```python
def test_weekly_is_noop():
    from jobs.market_hk import weekly
    assert weekly() == {}
    assert weekly(["00700.HK"]) == {}
```

- [ ] **Step 2: 跑测确认失败**

```bash
uv run pytest tests/test_market_hk.py::test_weekly_is_noop -v
```

Expected: FAIL — 仍 raise `NotImplementedError` 或旧测试名不存在时先确认旧测 FAIL。

- [ ] **Step 3: 实现**

`jobs/market_hk.py`：

```python
def weekly(tickers: list[str] | None = None) -> dict[str, str]:
    """港股周线未实现；Protocol 统一入口，no-op。CLI 未开放 --market hk。"""
    return {}
```

- [ ] **Step 4: README**

若有 `HK NotImplementedError` 文案，改为 `HK no-op`（与 intraday 一致）。

- [ ] **Step 5: 跑测**

```bash
uv run pytest tests/test_market_hk.py -v
```

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add jobs/market_hk.py tests/test_market_hk.py README.md
git commit -m "fix(hk): weekly no-op instead of NotImplementedError"
```

---

### Task 3: Intraday probe / batch 对齐 rate_limit

**Files:**
- Modify: `apis/yfinance/prices_intraday.py`
- Modify: `apis/yfinance/prices_us.py`（仅 docstring，若 Returns 顺序/措辞需对齐）
- Modify: `apis/yfinance/prices_us_weekly.py`（仅 docstring）
- Create: `tests/test_intraday_probe_rate_limit.py`

**Interfaces:**
- Produces: `_test_aapl_intraday(interval) -> tuple[date | None, str]` status ∈ `{ok, no_data, rate_limit, error}`
- Produces: `update_intraday(interval, full_rebase=False)` 在 `status == "rate_limit"` 时 `return {}`

- [ ] **Step 1: 写失败测**

`tests/test_intraday_probe_rate_limit.py`：

```python
"""Intraday AAPL probe rate_limit alignment with daily/weekly probes."""
from datetime import date
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest


@patch("apis.yfinance.prices_intraday.download_with_retry")
def test_test_aapl_intraday_rate_limit_from_exception(mock_dl):
    from apis.yfinance.prices_intraday import _test_aapl_intraday

    mock_dl.side_effect = Exception("YFRateLimitError: Too Many Requests")
    latest, status = _test_aapl_intraday("1h")
    assert latest is None
    assert status == "rate_limit"


@patch("apis.yfinance.prices_intraday.download_with_retry")
def test_test_aapl_intraday_empty_is_no_data_not_rate_limit(mock_dl):
    from apis.yfinance.prices_intraday import _test_aapl_intraday

    mock_dl.return_value = pd.DataFrame()
    latest, status = _test_aapl_intraday("1h")
    assert latest is None
    assert status == "no_data"


@patch("apis.yfinance.prices_intraday.download_with_retry")
def test_test_aapl_intraday_other_exception_is_error(mock_dl):
    from apis.yfinance.prices_intraday import _test_aapl_intraday

    mock_dl.side_effect = RuntimeError("boom")
    latest, status = _test_aapl_intraday("15m")
    assert latest is None
    assert status == "error"


@patch("apis.yfinance.prices_intraday.get_index_tickers")
@patch("apis.yfinance.prices_intraday._test_aapl_intraday")
def test_update_intraday_skips_on_rate_limit(mock_probe, mock_tickers):
    from apis.yfinance.prices_intraday import update_intraday

    mock_probe.return_value = (None, "rate_limit")
    mock_tickers.return_value = ["AAPL"]
    result = update_intraday("1h")
    assert result == {}
    # must not proceed to ticker universe work beyond probe
    mock_tickers.assert_not_called()
```

- [ ] **Step 2: 跑测确认失败**

```bash
uv run pytest tests/test_intraday_probe_rate_limit.py -v
```

Expected: FAIL — rate_limit 仍为 `error`；batch 可能误调 `get_index_tickers`。

- [ ] **Step 3: 实现 probe + batch**

`_test_aapl_intraday` docstring Returns 增加 `rate_limit`；except：

```python
    except Exception as e:
        err_msg = str(e)
        if "RateLimit" in err_msg or "Too Many Requests" in err_msg:
            log.warning(f"[AAPL {interval}] yfinance 被限速: {e}")
            return None, "rate_limit"
        log.error(f"[AAPL {interval}] 测试失败: {e}")
        return None, "error"
```

`update_intraday` 在 `status == "no_data"` 分支旁增加：

```python
    if status == "no_data":
        log.warning(f"[intraday {interval}] AAPL 无数据（周末/假期或未更新），跳过本次更新")
        return {}
    if status == "rate_limit":
        log.warning(f"[intraday {interval}] yfinance 被限速，跳过本次更新")
        return {}
    if status == "error":
        log.error(f"[intraday {interval}] AAPL 测试失败，跳过本次更新")
        return {}
```

（把原 `elif status == "error"` 改写成如上独立 `if`，避免漏 `rate_limit`。）

- [ ] **Step 4: 日线/周线 docstring 核对**

确认 `prices_us._test_aapl_data` / `prices_us_weekly._test_aapl_weekly` 的 Returns 含四态，且**无**「empty → rate_limit」表述。代码 except 已有则**不改逻辑**。

- [ ] **Step 5: 跑测**

```bash
uv run pytest tests/test_intraday_probe_rate_limit.py tests/test_intraday_updater_us.py -v
```

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add apis/yfinance/prices_intraday.py apis/yfinance/prices_us.py apis/yfinance/prices_us_weekly.py tests/test_intraday_probe_rate_limit.py
git commit -m "$(cat <<'EOF'
fix(yf): align intraday probe rate_limit with daily/weekly

Empty stays no_data; RateLimit in exception → rate_limit; batch skips.
EOF
)"
```

---

### Task 4: purge_index 单连接事务

**Files:**
- Modify: `modules/db_admin.py`
- Modify: `tests/test_db_admin.py`

**Interfaces:**
- Produces: `purge_index(index_id: str, *, dry_run: bool = True) -> dict[str, int]`
  - `dry_run=True`：仍 `count_index_rows`（`query`）
  - `dry_run=False`：`get_conn` 一次，多 DELETE，一次 `commit`；失败 `rollback` 再 raise

- [ ] **Step 1: 改/写失败测**

替换 `test_purge_index_deletes_all_index_tables`（不再 mock `execute` 逐表）：

```python
def test_purge_index_deletes_all_index_tables_in_one_transaction():
    from modules.db_admin import purge_index, _INDEX_PURGE_TABLES

    conn = MagicMock()
    cur = MagicMock()
    cur.rowcount = 2
    # support "with conn.cursor() as cur"
    conn.cursor.return_value.__enter__.return_value = cur
    conn.cursor.return_value.__exit__.return_value = None

    with patch("modules.db_admin.get_conn", return_value=conn) as mock_gc:
        deleted = purge_index("CSI800", dry_run=False)

    mock_gc.assert_called_once()
    assert cur.execute.call_count == len(_INDEX_PURGE_TABLES)
    for call, table in zip(cur.execute.call_args_list, _INDEX_PURGE_TABLES):
        sql, params = call[0][0], call[0][1]
        assert f"DELETE FROM {table}" in sql
        assert params == ("CSI800",)
    conn.commit.assert_called_once()
    conn.rollback.assert_not_called()
    conn.close.assert_called_once()
    assert all(v == 2 for v in deleted.values())
    assert set(deleted) == set(_INDEX_PURGE_TABLES)


def test_purge_index_rollback_on_mid_failure():
    from modules.db_admin import purge_index, _INDEX_PURGE_TABLES

    conn = MagicMock()
    cur = MagicMock()
    # fail on second DELETE
    def _exec(sql, params=None):
        if cur.execute.call_count == 2:
            raise RuntimeError("disk full")
        cur.rowcount = 1

    cur.execute.side_effect = _exec
    conn.cursor.return_value.__enter__.return_value = cur
    conn.cursor.return_value.__exit__.return_value = None

    with patch("modules.db_admin.get_conn", return_value=conn):
        import pytest
        with pytest.raises(RuntimeError, match="disk full"):
            purge_index("CSI800", dry_run=False)

    conn.rollback.assert_called_once()
    conn.commit.assert_not_called()
    conn.close.assert_called_once()
```

文件顶部确保：`from unittest.mock import patch, MagicMock`（按现有 import 补齐）。

保留 `test_purge_index_dry_run_counts_without_delete` 与 `test_purge_index_rejects_empty_id`。

- [ ] **Step 2: 跑测确认失败**

```bash
uv run pytest tests/test_db_admin.py -v -k purge
```

Expected: FAIL — 仍走 `execute()` 路径。

- [ ] **Step 3: 实现**

`modules/db_admin.py` 的 `purge_index` 在 `dry_run=False` 分支：

```python
    deleted: dict[str, int] = {}
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            for table in _INDEX_PURGE_TABLES:
                cur.execute(
                    f"DELETE FROM {table} WHERE index_id=%s",
                    (index_id,),
                )
                deleted[table] = int(cur.rowcount or 0)
        conn.commit()
        return deleted
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
```

`dry_run=True` 与校验逻辑不变。`get_conn` 已从 `core.db_client` import。

- [ ] **Step 4: 跑测**

```bash
uv run pytest tests/test_db_admin.py -v -k purge
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add modules/db_admin.py tests/test_db_admin.py
git commit -m "fix(db): purge_index deletes in a single transaction"
```

---

### Task 5: CLI `_format_run_result` + 删 `cmd_tushare_sync`

**Files:**
- Modify: `main.py`
- Modify: `tests/test_main_tushare_backfill.py`

**Interfaces:**
- Produces: `_format_run_result(result: Any) -> str`
- Removes: `cmd_tushare_sync`
- Dispatch `tushare sync` 仍 → `cmd_tushare_backfill(..., start=None)`（已有）

- [ ] **Step 1: 改测试**

`tests/test_main_tushare_backfill.py`：

1. 删除 `from main import ... cmd_tushare_sync`（若仅此一处引用）。
2. 替换 `test_tushare_sync_passes_no_start`：

```python
def test_tushare_sync_cli_dispatches_backfill_without_start():
    with patch("main.cmd_tushare_backfill", return_value=0) as backfill:
        rc = main_cli(["tushare", "sync", "--scope", "valuation", "--market", "cn"])

    assert rc == 0
    backfill.assert_called_once_with("valuation", "cn", False, start=None)
```

可选：增加 `_format_run_result` 单测（同文件或 test_cli）：

```python
def test_format_run_result_uses_render():
    from main import _format_run_result
    rep = MagicMock()
    rep.render.return_value = "hello"
    assert _format_run_result(rep) == "hello"


def test_format_run_result_falls_back_to_str():
    from main import _format_run_result
    assert _format_run_result(42) == "42"
```

- [ ] **Step 2: 实现 `main.py`**

```python
def _format_run_result(result: Any) -> str:
    render = getattr(result, "render", None)
    if callable(render):
        return render()
    return str(result)
```

`_run_buffered` 内：

```python
    print(_format_run_result(result))
```

**删除**整个 `cmd_tushare_sync` 函数。

全仓确认：

```bash
rg -n "cmd_tushare_sync" --type py
```

Expected: 仅历史注释或无匹配（测已改）。

- [ ] **Step 3: 跑测**

```bash
uv run pytest tests/test_main_tushare_backfill.py tests/test_cli.py -v
```

Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add main.py tests/test_main_tushare_backfill.py
git commit -m "$(cat <<'EOF'
refactor(cli): format buffered results; drop dead cmd_tushare_sync

tushare sync already dispatches to cmd_tushare_backfill(start=None).
EOF
)"
```

---

### Task 6: prices_index 写路径测 + SPEC/文档归档

**Files:**
- Modify: `tests/test_us_index_price.py`
- Modify: `docs/SPEC_code_review_followup.md`
- Modify: `docs/superpowers/specs/2026-07-12-code-review-closure-design.md`（状态）
- 核对：`README.md` / `CLAUDE.md` 无遗漏 daily/intraday 矛盾句

**Interfaces:**
- 测 `apis.yfinance.prices_index.update_index_prices() -> int`（mock I/O）

- [ ] **Step 1: 写路径测**

在 `tests/test_us_index_price.py` 追加（patch 缩短符号表，避免 14 次循环）：

```python
from datetime import date
from unittest.mock import patch, MagicMock
import pandas as pd


@patch("apis.yfinance.prices_index.execute")
@patch("apis.yfinance.prices_index.download_with_retry")
@patch("apis.yfinance.prices_index.query")
@patch("apis.yfinance.prices_index.last_us_trading_date", return_value=date(2026, 7, 10))
@patch(
    "apis.yfinance.prices_index.US_INDEX_SYMBOLS",
    [("^GSPC", "SP500")],
)
def test_update_index_prices_skips_when_up_to_date(
    mock_ltd, mock_query, mock_dl, mock_ex
):
    from apis.yfinance.prices_index import update_index_prices

    mock_query.return_value = [{"d": date(2026, 7, 10)}]
    assert update_index_prices() == 0
    mock_dl.assert_not_called()
    mock_ex.assert_not_called()


@patch("apis.yfinance.prices_index.execute", return_value=1)
@patch("apis.yfinance.prices_index.download_with_retry")
@patch("apis.yfinance.prices_index.query")
@patch("apis.yfinance.prices_index.last_us_trading_date", return_value=date(2026, 7, 11))
@patch(
    "apis.yfinance.prices_index.US_INDEX_SYMBOLS",
    [("^GSPC", "SP500")],
)
def test_update_index_prices_inserts_incremental_rows(
    mock_ltd, mock_query, mock_dl, mock_ex
):
    from apis.yfinance.prices_index import update_index_prices

    mock_query.return_value = [{"d": date(2026, 7, 10)}]
    df = pd.DataFrame(
        {
            "Date": [pd.Timestamp("2026-07-10"), pd.Timestamp("2026-07-11")],
            "Close": [5000.0, 5010.0],
        }
    )
    mock_dl.return_value = df

    n = update_index_prices()
    assert n == 1
    mock_dl.assert_called_once()
    mock_ex.assert_called_once()
    sql, rows = mock_ex.call_args[0][0], mock_ex.call_args[0][1]
    assert "INSERT IGNORE INTO index_prices" in sql
    # only date > last_date
    assert len(rows) == 1
    assert rows[0][0] == date(2026, 7, 11)
    assert rows[0][1] == "SP500"
    assert rows[0][2] == 5010.0


@patch("apis.yfinance.prices_index.execute")
@patch("apis.yfinance.prices_index.download_with_retry")
@patch("apis.yfinance.prices_index.query")
@patch("apis.yfinance.prices_index.last_us_trading_date", return_value=date(2026, 7, 11))
@patch(
    "apis.yfinance.prices_index.US_INDEX_SYMBOLS",
    [("^GSPC", "SP500"), ("QQQ", "QQQ")],
)
def test_update_index_prices_skips_symbol_on_download_error(
    mock_ltd, mock_query, mock_dl, mock_ex
):
    from apis.yfinance.prices_index import update_index_prices

    mock_query.return_value = [{"d": None}]
    mock_dl.side_effect = [
        Exception("network"),
        pd.DataFrame({"Date": [pd.Timestamp("2026-07-11")], "Close": [400.0]}),
    ]
    mock_ex.return_value = 1

    n = update_index_prices()
    assert n == 1
    assert mock_dl.call_count == 2
    mock_ex.assert_called_once()
```

注意：`prices_index` 用 `r["date"]`（列名 lower）。mock DataFrame 列经 lower 后为 `date`/`close`。上面 `Date`/`Close` 在代码里会 lower —— **实现测时若失败**，把 mock 列改成已 lower 的 `date`/`close`，并保证 `reset_index` 后有 `date` 列。更稳的构造：

```python
df = pd.DataFrame(
    {"date": [pd.Timestamp("2026-07-11")], "close": [5010.0]}
)
# download_with_retry 返回的 df 在代码里会 reset_index；若已有 date 列，
# reset_index 可能多出 index 列。对齐生产路径：index 为 DatetimeIndex。
df = pd.DataFrame(
    {"Close": [5010.0]},
    index=pd.DatetimeIndex([pd.Timestamp("2026-07-11")], name="Date"),
)
mock_dl.return_value = df
```

实现者跑测一次后按实际列处理微调 mock（行为断言不变：INSERT 一行 SP500）。

- [ ] **Step 2: 跑测**

```bash
uv run pytest tests/test_us_index_price.py -v
```

Expected: PASS（必要时微调 mock 形状）。

- [ ] **Step 3: 归档旧 SPEC**

`docs/SPEC_code_review_followup.md` 文件头改为：

```markdown
# Spec: Code-review 未决项跟进（已完成 / 已归档）

> **状态：已完成。** Phase 0–4 已落地。  
> **Closure：** `docs/superpowers/specs/2026-07-12-code-review-closure-design.md`  
> **Plan：** `docs/superpowers/plans/2026-07-12-code-review-closure.md`  
> 本文仅保留历史执行记录，**不再作为待办**。
```

删掉或改写「剩余项执行规格」类进行时措辞。

- [ ] **Step 4: design 状态**

`docs/superpowers/specs/2026-07-12-code-review-closure-design.md` 头：

```markdown
**状态:** 已实现
```

成功标准 checklist 可全部勾 `[x]`（实现者在全绿后勾）。

- [ ] **Step 5: 全量测试**

```bash
uv run pytest tests/ -q
```

Expected: 全绿（当前基线约 400+ passed）。

- [ ] **Step 6: Commit**

```bash
git add -f tests/test_us_index_price.py docs/SPEC_code_review_followup.md \
  docs/superpowers/specs/2026-07-12-code-review-closure-design.md \
  docs/superpowers/plans/2026-07-12-code-review-closure.md
# 若 README/CLAUDE 本 Task 还有补丁一并 add
git commit -m "$(cat <<'EOF'
test(docs): prices_index write-path coverage; archive review follow-up SPEC

Closure design marked implemented after full pytest green.
EOF
)"
```

（`docs/superpowers/` 在 `.gitignore`：对新文件用 `git add -f`。）

---

### Task 7: 最终核对（无新功能，仅验证）

**Files:** 无强制修改

- [ ] **Step 1: Spec 成功标准对照**

| 标准 | 验证命令/检查 |
|------|----------------|
| daily 不调 intraday | `rg -n "intraday" jobs/pipeline.py` → daily 内无调用 |
| HK weekly `{}` | `uv run pytest tests/test_market_hk.py::test_weekly_is_noop -q` |
| probe rate_limit | `uv run pytest tests/test_intraday_probe_rate_limit.py -q` |
| purge 事务 | `uv run pytest tests/test_db_admin.py -k purge -q` |
| 无 cmd_tushare_sync | `rg -n "cmd_tushare_sync" --type py` → 空 |
| prices_index 测 | `uv run pytest tests/test_us_index_price.py -q` |
| 全绿 | `uv run pytest tests/ -q` |

- [ ] **Step 2: 若有漏改文档，补 commit**

```bash
git status
# 有则 fixup 文档后 commit: docs: align remaining daily/intraday wording
```

- [ ] **Step 3: 完成**

无需空 commit。向用户报告：相对 design 的完成表 + 测试输出摘要。

---

## Self-Review (plan author)

| Spec § | Task |
|--------|------|
| 4.1 daily/intraday | Task 1 |
| 4.2 HK weekly | Task 2 |
| 4.3 probe + update_intraday | Task 3 |
| 4.4 purge 事务 | Task 4 |
| 4.5 format + 删 sync | Task 5 |
| 4.6 测 + SPEC | Task 6 |
| 成功标准 / 全量测 | Task 7 |

- 无 TBD/TODO 占位  
- 类型名与现码一致：`purge_index`、`_test_aapl_intraday`、`update_intraday`、`_format_run_result`  
- 明确 intraday **代码**补 `rate_limit`（非仅文档）  
- dry_run purge 仍走 `query`，不经事务路径  

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-12-code-review-closure.md`.

**Two execution options:**

1. **Subagent-Driven (recommended)** — fresh subagent per task, review between tasks  
2. **Inline Execution** — this session, executing-plans with checkpoints  

**Which approach?**
