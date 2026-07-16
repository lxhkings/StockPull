# Code-review Probe Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 收敛 yfinance AAPL probe 为 status-only 单核，并收完 code-review 残留 P1/P2（or_none 纯路径、market_cn 委托、docstring/空行/timeout），不合并日/周 batch。

**Architecture:** `probe_daily`/`probe_weekly` 改为返回 `str`；内部 `_is_rate_limit` + `_probe_has_date`（复用 `lower_ohlc_columns`）。`probe_intraday` 仍返回 `(Optional[date], str)`。生产调用方只读 status。P1 在语义等同处改 `or_none`；`update_index_price` 委托 `rebase_etf(full_rebase=False)`。

**Tech Stack:** Python 3.12, pytest, uv, pandas, unittest.mock

**Spec:** `docs/superpowers/specs/2026-07-16-code-review-probe-cleanup-design.md`

## Global Constraints

- **行为冻结：** empty → `no_data`；`rate_limit` 仅 except 含 `RateLimit` / `Too Many Requests`；batch 对 status 的 skip 映射不变（`error: rate_limit` / `error: no_data` / `error: test_failed`）。
- **不做：** 合并 `prices_us` / `prices_us_weekly` batch 编排；改表/算法/batch 大小；改 `transform_financial` / `transform_valuation` / shareholder 行门槛。
- **分层：** 不新增顶层包；probe 可 import `apis.yfinance.normalize`；禁止 import `jobs`。
- **测试：** mock `download_with_retry`；不连 Yahoo/NAS。
- **timeout：** probe daily/weekly/intraday 一律 `YF_TIMEOUT`（config，当前 60）。

---

## File Structure

| 文件 | 职责 |
|------|------|
| `apis/yfinance/probe.py` | P0：status-only daily/weekly；共享核；`_is_rate_limit` |
| `apis/yfinance/normalize.py` | 不改公开 API；被 probe 复用 `lower_ohlc_columns` |
| `apis/yfinance/prices_us.py` | `status = probe_daily(...)`；修 docstring |
| `apis/yfinance/prices_us_weekly.py` | 已是 `_` 解包 → 改为单 status；修 docstring |
| `apis/yfinance/prices_intraday.py` | 仅 docstring（P2）；probe 契约不变 |
| `jobs/market_cn.py` | `update_index_price` → `rebase_etf(full_rebase=False)` |
| `core/http_utils.py` | 删 `or_none` 后多余空行 |
| `apis/static/russell_ishares.py` | 列清洗用 `or_none` |
| `apis/futu/snapshot_daily.py` | `_num` → `or_none` |
| `apis/futu/backfill_earnings.py` | `_date_part`/payload 用 `or_none` |
| `tests/test_yf_probe.py` | status-only + hit/miss |
| `tests/test_stock_updater_us_weekly.py` | patch 返回 `str` |
| `tests/test_market_cn_etf_hook.py` | `full_rebase=False` 断言 |
| `tests/test_market_cn.py` | 可选：确认 `update_index_price` 仍委托（hook 测已覆盖） |

---

### Task 1: Probe 契约测（TDD 红）— status-only + hit/miss

**Files:**
- Modify: `tests/test_yf_probe.py`
- Test: `tests/test_yf_probe.py`

**Interfaces:**
- Consumes: （目标）`probe_daily(date) -> str`，`probe_weekly(date) -> str`，`probe_intraday(str) -> tuple[Optional[date], str]`
- Produces: 失败测驱动 Task 2 改签名

- [ ] **Step 1: 重写 `tests/test_yf_probe.py`**

完整替换文件内容为：

```python
"""Contract canaries for apis.yfinance.probe."""
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
def test_probe_intraday_other_exception_is_error(mock_dl):
    from apis.yfinance.probe import probe_intraday

    mock_dl.side_effect = RuntimeError("boom")
    latest, status = probe_intraday("15m")
    assert latest is None
    assert status == "error"


@patch("apis.yfinance.probe.download_with_retry")
def test_probe_daily_rate_limit(mock_dl):
    from apis.yfinance.probe import probe_daily

    mock_dl.side_effect = Exception("RateLimit")
    status = probe_daily(date(2026, 7, 10))
    assert status == "rate_limit"


@patch("apis.yfinance.probe.download_with_retry")
def test_probe_weekly_rate_limit(mock_dl):
    from apis.yfinance.probe import probe_weekly

    mock_dl.side_effect = Exception("Too Many Requests")
    status = probe_weekly(date(2026, 7, 6))
    assert status == "rate_limit"


@patch("apis.yfinance.probe.download_with_retry")
def test_probe_daily_hit_target_date(mock_dl):
    from apis.yfinance.probe import probe_daily

    idx = pd.DatetimeIndex([pd.Timestamp("2026-07-10")], name="Date")
    mock_dl.return_value = pd.DataFrame(
        {"Open": [1.0], "High": [1.0], "Low": [1.0], "Close": [1.0], "Volume": [1]},
        index=idx,
    )
    status = probe_daily(date(2026, 7, 10))
    assert status == "ok"
    assert mock_dl.call_args.kwargs.get("timeout") is not None
    from config import YF_TIMEOUT
    assert mock_dl.call_args.kwargs["timeout"] == YF_TIMEOUT


@patch("apis.yfinance.probe.download_with_retry")
def test_probe_daily_miss_target_date(mock_dl):
    from apis.yfinance.probe import probe_daily

    idx = pd.DatetimeIndex([pd.Timestamp("2026-07-09")], name="Date")
    mock_dl.return_value = pd.DataFrame(
        {"Open": [1.0], "High": [1.0], "Low": [1.0], "Close": [1.0], "Volume": [1]},
        index=idx,
    )
    status = probe_daily(date(2026, 7, 10))
    assert status == "no_data"


@patch("apis.yfinance.probe.download_with_retry")
def test_probe_daily_empty_is_no_data(mock_dl):
    from apis.yfinance.probe import probe_daily

    mock_dl.return_value = pd.DataFrame()
    assert probe_daily(date(2026, 7, 10)) == "no_data"


@patch("apis.yfinance.probe.download_with_retry")
def test_probe_weekly_hit_target_monday(mock_dl):
    from apis.yfinance.probe import probe_weekly

    idx = pd.DatetimeIndex([pd.Timestamp("2026-07-06")], name="Date")
    mock_dl.return_value = pd.DataFrame(
        {"Open": [1.0], "High": [1.0], "Low": [1.0], "Close": [1.0], "Volume": [1]},
        index=idx,
    )
    assert probe_weekly(date(2026, 7, 6)) == "ok"
```

- [ ] **Step 2: 跑测，确认 daily/weekly 新契约失败**

```bash
uv run pytest tests/test_yf_probe.py -v
```

Expected: `test_probe_daily_rate_limit` / `test_probe_weekly_rate_limit` FAIL（仍返回 tuple，或解包错误）；hit/miss 测 FAIL 或因返回 tuple 断言失败。intraday 测应仍 PASS。

- [ ] **Step 3: Commit（红测可提交为测试先行）**

```bash
git add tests/test_yf_probe.py
git commit -m "$(cat <<'EOF'
test(yf): tighten probe contract tests to status-only

EOF
)"
```

---

### Task 2: 实现 probe 单核 + 调用方

**Files:**
- Modify: `apis/yfinance/probe.py`（整文件重写结构）
- Modify: `apis/yfinance/prices_us.py`（约 61 行）
- Modify: `apis/yfinance/prices_us_weekly.py`（约 72 行）
- Modify: `tests/test_stock_updater_us_weekly.py`（74、82、90 行 patch）
- Test: `tests/test_yf_probe.py`, `tests/test_stock_updater_us_weekly.py`

**Interfaces:**
- Consumes: `apis.yfinance.normalize.lower_ohlc_columns`, `config.YF_TIMEOUT`, `download_with_retry`
- Produces:
  - `probe_daily(target_date: date) -> str`
  - `probe_weekly(target_monday: date) -> str`
  - `probe_intraday(interval: str) -> tuple[Optional[date], str]`
  - `_is_rate_limit(exc: BaseException) -> bool`（模块内私有即可）
  - `_probe_has_date(...) -> str`（模块内私有）

- [ ] **Step 1: 重写 `apis/yfinance/probe.py`**

完整替换为：

```python
"""AAPL readiness probes for yfinance US feeds. Status: ok|no_data|rate_limit|error."""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Optional

import pandas as pd

from config import YF_TIMEOUT
from apis.yfinance.client import download_with_retry
from apis.yfinance.normalize import lower_ohlc_columns

log = logging.getLogger(__name__)

# interval → yfinance 参数字符串（probe + prices_intraday 共用）
YF_INTERVAL_MAP: dict[str, str] = {
    "15m": "15m",
    "1h": "60m",
}

# interval → yfinance 免费 tier 最大可拉天数
INTERVAL_LOOKBACK_DAYS: dict[str, int] = {
    "15m": 60,
    "1h": 730,
}


def _is_rate_limit(exc: BaseException) -> bool:
    msg = str(exc)
    return "RateLimit" in msg or "Too Many Requests" in msg


def _probe_has_date(
    *,
    interval: str,
    start: date,
    end: date,
    target: date,
    context: str,
) -> str:
    """Download AAPL OHLCV window; return ok if target date present."""
    try:
        df = download_with_retry(
            tickers="AAPL",
            start=start.strftime("%Y-%m-%d"),
            end=end.strftime("%Y-%m-%d"),
            interval=interval,
            group_by="column",
            threads=False,
            timeout=YF_TIMEOUT,
            context=context,
        )
        if df is None or df.empty:
            return "no_data"

        df = lower_ohlc_columns(df.reset_index())
        if "date" not in df.columns:
            for cand in ("datetime", "index"):
                if cand in df.columns:
                    df = df.rename(columns={cand: "date"})
                    break
        if "date" not in df.columns:
            return "no_data"

        dates = pd.to_datetime(df["date"]).dt.date
        if target in set(dates):
            return "ok"
        return "no_data"
    except Exception as e:
        if _is_rate_limit(e):
            log.warning(f"{context}yfinance 被限速: {e}")
            return "rate_limit"
        log.warning(f"{context}测试请求失败: {e}")
        return "error"


def probe_daily(target_date: date) -> str:
    """Test whether yfinance has daily bars for target_date (AAPL probe)."""
    end_dt = target_date + timedelta(days=1)
    start_dt = target_date - timedelta(days=5)
    return _probe_has_date(
        interval="1d",
        start=start_dt,
        end=end_dt,
        target=target_date,
        context="[AAPL probe] ",
    )


def probe_weekly(target_monday: date) -> str:
    """Test whether yfinance has weekly bar for week starting target_monday."""
    start = target_monday - timedelta(days=14)
    end = target_monday + timedelta(days=7)
    return _probe_has_date(
        interval="1wk",
        start=start,
        end=end,
        target=target_monday,
        context="[AAPL weekly probe] ",
    )


def probe_intraday(interval: str) -> tuple[Optional[date], str]:
    """
    测试 AAPL 是否有最近交易日数据，判断 yfinance intraday API 是否可用

    Returns:
        (latest_date, status) 其中 status 为:
        - "ok": 有数据，返回最新日期
        - "no_data": 无数据（周末/假期或未更新）
        - "rate_limit": 被限速
        - "error": 其他错误
    """
    try:
        today = date.today()
        floor = today - timedelta(days=INTERVAL_LOOKBACK_DAYS[interval] - 1)
        end = today + timedelta(days=1)

        df = download_with_retry(
            tickers="AAPL",
            start=floor.strftime("%Y-%m-%d"),
            end=end.strftime("%Y-%m-%d"),
            interval=YF_INTERVAL_MAP[interval],
            group_by="ticker",
            threads=False,
            timeout=YF_TIMEOUT,
            context=f"[AAPL {interval} probe] ",
        )

        if df is None or df.empty:
            return None, "no_data"

        latest = df.index[-1].date()
        log.info(f"[AAPL {interval}] 测试成功：最新日期 {latest}，范围 {floor} ~ {latest}")
        return latest, "ok"

    except Exception as e:
        if _is_rate_limit(e):
            log.warning(f"[AAPL {interval}] yfinance 被限速: {e}")
            return None, "rate_limit"
        log.error(f"[AAPL {interval}] 测试失败: {e}")
        return None, "error"
```

- [ ] **Step 2: 改 `prices_us.py` 调用**

将：

```python
    test_df, status = probe_daily(last_trading)
```

改为：

```python
    status = probe_daily(last_trading)
```

- [ ] **Step 3: 改 `prices_us_weekly.py` 调用**

将：

```python
    _, status = probe_weekly(target_monday)
```

改为：

```python
    status = probe_weekly(target_monday)
```

- [ ] **Step 4: 改 weekly batch 测的 patch 返回值**

`tests/test_stock_updater_us_weekly.py` 三处：

```python
patch("apis.yfinance.prices_us_weekly.probe_weekly", return_value="rate_limit")
# ...
patch("apis.yfinance.prices_us_weekly.probe_weekly", return_value="no_data")
# ...
patch("apis.yfinance.prices_us_weekly.probe_weekly", return_value="error")
```

（删掉 `return_value=(None, "...")` 元组。）

- [ ] **Step 5: 跑测绿**

```bash
uv run pytest tests/test_yf_probe.py tests/test_stock_updater_us_weekly.py \
  tests/test_intraday_probe_rate_limit.py tests/test_intraday_updater_us.py -v
```

Expected: PASS（全部）。

- [ ] **Step 6: 静态验收**

```bash
rg -n "test_df" apis/yfinance/prices_us.py
rg -n "timeout=30" apis/yfinance/probe.py
rg -n "def probe_daily|def probe_weekly" apis/yfinance/probe.py
```

Expected: 前两行无匹配；后一行签名为 `-> str`。

- [ ] **Step 7: Commit**

```bash
git add apis/yfinance/probe.py apis/yfinance/prices_us.py \
  apis/yfinance/prices_us_weekly.py tests/test_stock_updater_us_weekly.py
git commit -m "$(cat <<'EOF'
refactor(yf): probe daily/weekly status-only with shared core

EOF
)"
```

---

### Task 3: P1 — market_cn 委托 + or_none 纯路径

**Files:**
- Modify: `jobs/market_cn.py`（`update_index_price`）
- Modify: `tests/test_market_cn_etf_hook.py`
- Modify: `apis/static/russell_ishares.py`（约 247 行）
- Modify: `apis/futu/snapshot_daily.py`（`_num`）
- Modify: `apis/futu/backfill_earnings.py`（`_date_part` + payload）
- Test: `tests/test_market_cn_etf_hook.py`（及现有 futu/static 测若有）

**Interfaces:**
- Consumes: `core.http_utils.or_none`, `jobs.market_cn.rebase_etf`
- Produces: `update_index_price() -> int` 经 `rebase_etf(full_rebase=False)`

- [ ] **Step 1: 改 etf hook 断言（先红后绿）**

`tests/test_market_cn_etf_hook.py`：

```python
"""Verify update_index_price() only runs sector ETF updater."""
from unittest.mock import patch


@patch("apis.tushare.etf_cn.update_etf_prices")
def test_update_index_price_calls_etf_updater_only(mock_etf_update):
    """CN index_prices path is sector ETFs only (no CSI800 / index_daily)."""
    mock_etf_update.return_value = 42

    from jobs.market_cn import update_index_price
    total = update_index_price()

    assert total == 42
    mock_etf_update.assert_called_once_with(full_rebase=False)
```

- [ ] **Step 2: 跑 hook 测确认红**

```bash
uv run pytest tests/test_market_cn_etf_hook.py -v
```

Expected: FAIL（当前 `assert_called_once_with()` 无 kwargs，或调用参数不匹配——在改 market 前：若仍 `update_etf_prices()` 无参则 assertion 失败）。

- [ ] **Step 3: 改 `jobs/market_cn.py`**

将 `update_index_price` 换成：

```python
def update_index_price() -> int:
    """行业 ETF 后复权日线 → index_prices（index_id = ts_code）。无宽基指数价。"""
    return rebase_etf(full_rebase=False)
```

保持 `rebase_etf` 为唯一 `from apis.tushare.etf_cn import update_etf_prices` 处：

```python
def rebase_etf(*, full_rebase: bool = True) -> int:
    """行业 ETF index_prices 全量/增量重灌。非 MarketModule；仅 CLI --etf-only。"""
    from apis.tushare.etf_cn import update_etf_prices
    return update_etf_prices(full_rebase=full_rebase)
```

（`update_index_price` 不再单独 import `update_etf_prices`。）

- [ ] **Step 4: 跑 hook + market_cn 测**

```bash
uv run pytest tests/test_market_cn_etf_hook.py tests/test_market_cn.py -v
```

Expected: PASS。

- [ ] **Step 5: `russell_ishares` 列清洗**

在 `apis/static/russell_ishares.py` 顶部 imports 增加（若尚未有）：

```python
from core.http_utils import or_none
```

将：

```python
    for col in df.columns:
        df[col] = [None if pd.isna(v) else v for v in df[col]]
```

改为：

```python
    for col in df.columns:
        df[col] = [or_none(v) for v in df[col]]
```

- [ ] **Step 6: `futu/snapshot_daily.py`**

增加：

```python
from core.http_utils import or_none
```

将 `_num` 改为：

```python
def _num(v):
    return or_none(v)
```

（若 `_num` 仅此逻辑，也可在调用处直接 `or_none`；优先保留 `_num` 名以免大 diff，实现委托 `or_none`。）

- [ ] **Step 7: `futu/backfill_earnings.py`**

增加：

```python
from core.http_utils import or_none
```

将 `_date_part` 改为：

```python
def _date_part(s):
    """'2026-04-30 17:00:00' -> '2026-04-30'；空值返回 None。"""
    s = or_none(s)
    if s is None:
        return None
    s = str(s).strip()
    return s.split(" ")[0] if s else None
```

将 payload 行改为：

```python
        payload = {k: or_none(v) for k, v in r.items()}
```

- [ ] **Step 8: 相关测**

```bash
uv run pytest tests/test_market_cn_etf_hook.py tests/test_market_cn.py \
  tests/test_index_updater_russell1000.py -v
```

若存在 futu earnings/snapshot 单测一并跑：

```bash
uv run pytest tests/ -k "earnings or snapshot_daily or russell" -v --tb=short
```

Expected: PASS（无行为变更）。

- [ ] **Step 9: Commit**

```bash
git add jobs/market_cn.py tests/test_market_cn_etf_hook.py \
  apis/static/russell_ishares.py apis/futu/snapshot_daily.py \
  apis/futu/backfill_earnings.py
git commit -m "$(cat <<'EOF'
refactor: or_none pure paths and CN update_index_price via rebase_etf

EOF
)"
```

---

### Task 4: P2 — docstring / 空行 + 全量验收

**Files:**
- Modify: `apis/yfinance/prices_us.py`（模块 docstring）
- Modify: `apis/yfinance/prices_us_weekly.py`（模块 docstring + 文件首行注释）
- Modify: `apis/yfinance/prices_intraday.py`（模块 docstring）
- Modify: `core/http_utils.py`（`or_none` 后多余空行）

**Interfaces:**
- Consumes: 无
- Produces: 文档与空白整理；无 API 变更

- [ ] **Step 1: 替换三 prices 文件头**

`apis/yfinance/prices_us.py` 顶部改为：

```python
"""US equity daily prices via yfinance (incremental by sync_log).

Writes prices table; batch entry for pipeline. INSERT IGNORE on (ticker, date).
"""
```

`apis/yfinance/prices_us_weekly.py` 顶部改为（删掉 `# data/stock_updater_us_weekly.py` 行）：

```python
"""US equity weekly prices via yfinance (interval=1wk).

Writes prices_weekly; sync_log data_type price_weekly.
Mirrors prices_us batch structure; differs in interval, table, data_type.
"""
```

`apis/yfinance/prices_intraday.py` 顶部改为：

```python
"""US equity intraday prices via yfinance free tier (15m / 1h).

Writes prices_intraday; sync_log data_type intraday_15m / intraday_60m.
"""
```

- [ ] **Step 2: `core/http_utils.py`**

确保 `or_none` 与 `to_date` 之间只有**一个**空行（删除双重空行）：

```python
    return value


def to_date(value) -> Optional[str]:
```

并删除 `to_date` 与 `format_cik` 之间多余的第二空行（若仍存在双空行，压成单空行）。

- [ ] **Step 3: 全量验收命令**

```bash
rg -n "test_df" apis/yfinance/prices_us.py
rg -n "timeout=30" apis/yfinance/probe.py
rg -n "stock_updater" apis/yfinance/prices_us.py apis/yfinance/prices_us_weekly.py apis/yfinance/prices_intraday.py
rg -n "from apis.tushare.etf_cn import update_etf_prices" jobs/market_cn.py
```

Expected:

- `test_df` / `timeout=30` / prices 内 `stock_updater`：无匹配  
- `update_etf_prices` import：仅出现在 `rebase_etf` 内一行  

```bash
uv run pytest tests/test_yf_probe.py tests/test_stock_updater_us_weekly.py \
  tests/test_intraday_probe_rate_limit.py tests/test_intraday_updater_us.py \
  tests/test_market_cn.py tests/test_market_cn_etf_hook.py \
  tests/test_http_utils.py tests/test_index_updater_russell1000.py -v
```

Expected: PASS。

- [ ] **Step 4: Commit**

```bash
git add apis/yfinance/prices_us.py apis/yfinance/prices_us_weekly.py \
  apis/yfinance/prices_intraday.py core/http_utils.py
git commit -m "$(cat <<'EOF'
chore: refresh yfinance module headers and http_utils spacing

EOF
)"
```

- [ ] **Step 5: 可选 — 标记 design 已实现**

将 `docs/superpowers/specs/2026-07-16-code-review-probe-cleanup-design.md` 状态改为 `已实现`，commit：

```bash
git add docs/superpowers/specs/2026-07-16-code-review-probe-cleanup-design.md
git commit -m "$(cat <<'EOF'
docs: mark probe cleanup design implemented

EOF
)"
```

---

## Self-Review (plan author)

| Spec 要求 | Task |
|-----------|------|
| P0 status-only daily/weekly | Task 1–2 |
| `_is_rate_limit` + `_probe_has_date` + `lower_ohlc_columns` | Task 2 |
| `YF_TIMEOUT` 统一 | Task 2 |
| 删 `test_df` | Task 2 |
| hit/miss 测 | Task 1 |
| weekly patch str | Task 2 |
| `update_index_price` → `rebase_etf(False)` | Task 3 |
| or_none: russell / futu snapshot / earnings | Task 3 |
| 不碰 financial/valuation/shareholder 门槛 | Task 3 明确不改 |
| docstring + 空行 | Task 4 |
| 无 batch 合并 | 无 task 动编排逻辑 |

无 TBD/TODO 占位；签名在 Task 2 Interfaces 与测试一致。
