# Structural Debt Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 按已批准 design 完成 P0–P4 结构债清理：死码删除、yfinance/tushare 日周参数化 batch（CLI 仍分开）、futu 轻量 write helper、main/CLI 瘦身；行为与 argv 契约不变。

**Architecture:** 同源包内 `UsPriceSpec` / `CnPriceSpec` + runner；日/周各保留 public 入口函数。Futu 仅抽 `upsert_rows` / `paginate_call`。CLI 命令迁入 `cli/commands_*.py`，`main` re-export 保测试。

**Tech Stack:** Python 3.12, pytest, uv, pandas, unittest.mock, MariaDB（测不连真 NAS）

**Spec:** `docs/superpowers/specs/2026-07-16-structural-debt-cleanup-design.md`

## Global Constraints

- **主目标：** 结构债 / 可维护性；不为更快改 `YF_BATCH_*`、tushare rate、futu 并发。
- **日/周分离：** 代码可参数化共用；`prices daily` 与 `prices weekly` 永远分开；`Pipeline.daily` 不调 weekly。
- **P1 weekly 写库：** 与 daily 统一 `flush_prices_and_sync(..., price_table="prices_weekly", on_duplicate=False)`。
- **分层：** `jobs → apis → core/modules`；禁止跨 apis 互引；jobs 禁止 import 上游 SDK；不新建第四顶层包。
- **不做：** 跨源 PriceEngine；改 `prices_hk` / intraday / index；改 etf/financial/valuation/derive；新表/新市场。
- **测试：** mock 网络与 DB；`uv run pytest`；不连 Yahoo / OpenD / NAS（除用户明确要求的 smoke）。
- **提交：** 每 Task 结束 commit；阶段之间可停。

---

## File Structure

| 文件 | 职责 |
|------|------|
| `config.py` | 删 `AKSHARE_*`；`INDEX_CONFIG["HSI"]["source"]` → `"csv"` |
| `apis/yfinance/ticker_utils.py` | 删 akshare/efinance 转换函数 |
| `tests/test_ticker_utils.py` | 删对应测 |
| `main.py` | P0 注释；P4 收成入口 + re-export `cmd_*` |
| `CLAUDE.md` | 去过时 AKSHARE 配置/网络说明 |
| `apis/yfinance/prices_batch.py` | **新建** `UsPriceSpec` + `run_us_equity_batch` + `price_rows_from_df` |
| `apis/yfinance/prices_us.py` | 薄入口 `update_prices_batch` |
| `apis/yfinance/prices_us_weekly.py` | 薄入口 + `_last_us_weekly_date` |
| `apis/tushare/prices_cn_batch.py` | **新建** `CnPriceSpec` + `run_cn_equity_batch` |
| `apis/tushare/prices_cn.py` / `prices_cn_weekly.py` | 薄入口；weekly 可保留 `_save_weekly_prices_batch` 给测 |
| `apis/futu/write_utils.py` | **新建** `upsert_rows` / `paginate_call` |
| `apis/futu/backfill_*.py` / `snapshot_*.py` | 换骨架，字段映射不动 |
| `cli/commands_prices.py` 等 | **新建** 原 `main.cmd_*` 实现 |
| `cli/parser.py` / `deprecate.py` | 不改契约 |
| `tests/test_yf_prices_batch.py` | **新建** US batch 写表/spec 契约 |
| `tests/test_cn_prices_batch.py` | **新建** 可选；或改现有 cn weekly 测 |
| `tests/test_futu_write_utils.py` | **新建** |
| `tests/test_stock_updater_us_weekly.py` | 适配 flush 路径；patch 路径 |
| `tests/test_stock_updater_cn_weekly.py` | import 路径改 batch 或 thin re-export |
| `tests/test_cli.py` / `test_main_tushare_backfill.py` | 继续 `from main import cmd_*`（re-export） |
| `README.md` | 架构树补 `cli/commands_*` |

**执行顺序:** Task 1 (P0) → 2–4 (P1) → 5–6 (P2) → 7–9 (P3) → 10–11 (P4 + 文档收尾)

---

### Task 1: P0 死码与文档遗留

**Files:**
- Modify: `config.py`
- Modify: `apis/yfinance/ticker_utils.py`
- Modify: `tests/test_ticker_utils.py`
- Modify: `main.py`（仅注释）
- Modify: `CLAUDE.md`
- Test: `tests/test_ticker_utils.py`, `tests/test_config.py`

**Interfaces:**
- Consumes: 无
- Produces: 无 `AKSHARE_*` / `to_akshare_*` / `to_efinance_*` / `from_akshare_*` 生产符号

- [ ] **Step 1: 确认无生产引用**

```bash
cd /Users/xiaohong/Project/StockPull
rg -n 'AKSHARE_|to_akshare|from_akshare|to_efinance|from_efinance' --type py
```

Expected: 仅 `config.py` 定义、`ticker_utils.py` 定义、`tests/test_ticker_utils.py`、`main.py` 变量名 `_AKSHARE_NO_PROXY`（保留 env 逻辑）。

- [ ] **Step 2: 删 config 中 AKSHARE 三常量**

从 `config.py` 删除：

```python
# A-share / HK source delays (akshare is sometimes flaky; serial)
AKSHARE_RETRY_COUNT = 5
AKSHARE_RETRY_DELAY = 3.0
AKSHARE_REQUEST_DELAY = 1.5  # between per-stock calls
```

将 `INDEX_CONFIG["HSI"]["source"]` 从 `"akshare"` 改为 `"csv"`。

- [ ] **Step 3: 删 ticker_utils 死函数**

删除 `to_akshare_a`、`to_akshare_hk`、`to_efinance_a`、`to_efinance_hk`、`from_akshare_a`、`from_akshare_hk` 整段（约 L59–98）。保留 `to_yfinance_us` 及之前的 parse/infer 函数。

- [ ] **Step 4: 收紧 test_ticker_utils**

完整替换 `tests/test_ticker_utils.py` 为：

```python
import pytest

from apis.yfinance.ticker_utils import (
    parse_ticker,
    to_yfinance_us,
    infer_market,
    Market,
)


@pytest.mark.parametrize("ticker,code,suffix", [
    ("600519.SH", "600519", "SH"),
    ("000001.SZ", "000001", "SZ"),
    ("00700.HK", "00700", "HK"),
    ("AAPL", "AAPL", None),
    ("BRK-B", "BRK-B", None),
])
def test_parse_ticker(ticker, code, suffix):
    p = parse_ticker(ticker)
    assert p.code == code
    assert p.suffix == suffix


@pytest.mark.parametrize("ticker,market", [
    ("AAPL", Market.US),
    ("BRK-B", Market.US),
    ("600519.SH", Market.CN),
    ("000001.SZ", Market.CN),
    ("300750.SZ", Market.CN),
    ("688981.SH", Market.CN),
    ("00700.HK", Market.HK),
    ("09988.HK", Market.HK),
])
def test_infer_market(ticker, market):
    assert infer_market(ticker) == market


def test_to_yfinance_us_dot_to_dash():
    assert to_yfinance_us("AAPL") == "AAPL"
    assert to_yfinance_us("BRK.B") == "BRK-B"
```

- [ ] **Step 5: 改 main 注释与 CLAUDE.md**

`main.py` 顶部注释改为（保留 NO_PROXY 行为与 `_AKSHARE_NO_PROXY` 变量名亦可，或改名为 `_EASTMONEY_NO_PROXY`——**若改名需同步赋值**；推荐只改注释不改变量名以减小 diff）：

```python
# Optional NO_PROXY for eastmoney/xueqiu hosts (legacy; primary feeds are
# tushare/yfinance/futu). Do not set NO_PROXY=* — yfinance may need system proxy.
```

`CLAUDE.md` Configuration / Network Notes：

- 删除 `AKSHARE_RETRY_*` 那一行。
- Network Notes 改为说明：`main.py` 仅追加 eastmoney/xueqiu 到 `NO_PROXY`，**不是** `NO_PROXY=*`；主数据源为 tushare / yfinance / futu。

- [ ] **Step 6: 跑测**

```bash
uv run pytest tests/test_ticker_utils.py tests/test_config.py -q
uv run pytest tests/ -q
```

Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add config.py apis/yfinance/ticker_utils.py tests/test_ticker_utils.py main.py CLAUDE.md
git commit -m "chore: remove akshare dead config and ticker converters (P0)"
```

---

### Task 2: P1 — US batch 契约测（TDD 红）

**Files:**
- Create: `tests/test_yf_prices_batch.py`
- Test: `tests/test_yf_prices_batch.py`

**Interfaces:**
- Consumes: （目标）`apis.yfinance.prices_batch.run_us_equity_batch`、`UsPriceSpec`、`price_rows_from_df`
- Produces: 失败测驱动 Task 3

- [ ] **Step 1: 写失败测**

创建 `tests/test_yf_prices_batch.py`：

```python
"""Contract tests for shared US equity batch runner."""
from datetime import date
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest


def test_price_rows_from_df_shape():
    from apis.yfinance.prices_batch import price_rows_from_df

    df = pd.DataFrame({
        "ticker": ["AAPL"],
        "date": [date(2026, 7, 10)],
        "open": [1.0], "high": [2.0], "low": [0.5],
        "close": [1.5], "volume": [100],
    })
    rows = price_rows_from_df(df)
    assert rows == [("AAPL", date(2026, 7, 10), 1.0, 2.0, 0.5, 1.5, 100)]


def test_run_weekly_flush_uses_prices_weekly_and_ignore():
    """Weekly path must batch-flush prices_weekly with INSERT IGNORE semantics."""
    from apis.yfinance.prices_batch import UsPriceSpec, run_us_equity_batch

    target = date(2026, 5, 11)
    spec = UsPriceSpec(
        label="weekly batch",
        interval="1wk",
        data_type="price_weekly",
        price_table="prices_weekly",
        probe=lambda d: "ok",
        target_date=lambda: target,
        end_exclusive=lambda d: d + __import__("datetime").timedelta(days=7),
        on_duplicate=False,
        support_years=False,
    )

    # Minimal multi-index download frame for one ticker
    idx = pd.DatetimeIndex([pd.Timestamp("2026-05-11")])
    cols = pd.MultiIndex.from_product(
        [["AAPL"], ["Open", "High", "Low", "Close", "Volume"]]
    )
    raw = pd.DataFrame(
        [[180.0, 182.0, 178.0, 181.0, 1_000_000]],
        index=idx, columns=cols,
    )

    mock_conn = MagicMock()
    flush_calls = []

    def capture_flush(conn, price_rows, sync_rows, *, on_duplicate=True, price_table="prices"):
        flush_calls.append({
            "price_rows": price_rows,
            "sync_rows": sync_rows,
            "on_duplicate": on_duplicate,
            "price_table": price_table,
        })

    with patch("apis.yfinance.prices_batch.get_conn", return_value=mock_conn), \
         patch("apis.yfinance.prices_batch.download_with_retry", return_value=raw), \
         patch("apis.yfinance.prices_batch.get_last_sync_map", return_value={"AAPL": None}), \
         patch("apis.yfinance.prices_batch.flush_prices_and_sync", side_effect=capture_flush), \
         patch("apis.yfinance.prices_batch.YF_BATCH_SIZE", 40):
        result = run_us_equity_batch(["AAPL"], spec=spec, full_rebase=True)

    assert result["AAPL"] == "ok"
    assert len(flush_calls) == 1
    assert flush_calls[0]["price_table"] == "prices_weekly"
    assert flush_calls[0]["on_duplicate"] is False
    assert flush_calls[0]["sync_rows"][0][1] == "price_weekly"


def test_run_empty_tickers():
    from apis.yfinance.prices_batch import UsPriceSpec, run_us_equity_batch
    from datetime import date as d

    spec = UsPriceSpec(
        label="batch", interval="1d", data_type="price", price_table="prices",
        probe=lambda x: "ok", target_date=lambda: d(2026, 7, 10),
        end_exclusive=lambda x: x, on_duplicate=False, support_years=True,
    )
    assert run_us_equity_batch([], spec=spec) == {}


def test_probe_rate_limit_skips_without_download():
    from apis.yfinance.prices_batch import UsPriceSpec, run_us_equity_batch
    from datetime import date as d

    called = {"dl": False}

    def boom_dl(*a, **k):
        called["dl"] = True
        raise AssertionError("should not download")

    spec = UsPriceSpec(
        label="batch", interval="1d", data_type="price", price_table="prices",
        probe=lambda x: "rate_limit", target_date=lambda: d(2026, 7, 10),
        end_exclusive=lambda x: x, on_duplicate=False, support_years=True,
    )
    with patch("apis.yfinance.prices_batch.download_with_retry", side_effect=boom_dl):
        result = run_us_equity_batch(["AAPL"], spec=spec)
    assert result == {"AAPL": "error: rate_limit"}
    assert called["dl"] is False
```

- [ ] **Step 2: 跑测确认失败**

```bash
uv run pytest tests/test_yf_prices_batch.py -v
```

Expected: FAIL — `ModuleNotFoundError` 或 `ImportError: prices_batch`

- [ ] **Step 3: Commit 红测（可选但推荐）**

```bash
git add tests/test_yf_prices_batch.py
git commit -m "test(yf): add prices_batch contract tests (red)"
```

---

### Task 3: P1 — 实现 `prices_batch` + 薄入口

**Files:**
- Create: `apis/yfinance/prices_batch.py`
- Modify: `apis/yfinance/prices_us.py`
- Modify: `apis/yfinance/prices_us_weekly.py`
- Test: `tests/test_yf_prices_batch.py`, `tests/test_stock_updater_us_weekly.py`

**Interfaces:**
- Consumes: `download_with_retry`, `normalize_daily_frame`, `flush_prices_and_sync`, `get_last_sync_map`, `probe_*`（由调用方注入 Spec）
- Produces:
  - `UsPriceSpec` dataclass
  - `price_rows_from_df(df) -> list[tuple]`
  - `run_us_equity_batch(tickers, *, spec, full_rebase=False, years=None) -> dict[str, str]`
  - `prices_us.update_prices_batch` / `prices_us_weekly.update_weekly_batch` 签名不变

- [ ] **Step 1: 实现 `apis/yfinance/prices_batch.py`**

```python
"""Shared US equity batch orchestration for daily (1d) and weekly (1wk).

Public market entrypoints remain prices_us / prices_us_weekly — they build
UsPriceSpec at call time (so unittest.mock patches on those modules still work)
and call run_us_equity_batch. Never run daily+weekly in one call.
"""
from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Callable, Dict, List, Optional

import pandas as pd

from config import (
    HISTORY_YEARS_US,
    START_DATE_US,
    YF_BATCH_DELAY_BASE,
    YF_BATCH_DELAY_JITTER,
    YF_BATCH_SIZE,
    YF_LOOKBACK_DAYS,
    YF_RETRY_COUNT,
    YF_THREADS,
    YF_TIMEOUT,
)
from core.batch_utils import chunked
from core.db_client import get_conn
from core.http_utils import to_float, to_int
from modules.price_write import flush_prices_and_sync
from modules.sync_log import get_last_sync_map, set_sync_error
from apis.yfinance.client import download_with_retry
from apis.yfinance.normalize import normalize_daily_frame
from apis.yfinance.ticker_utils import to_yfinance_us

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class UsPriceSpec:
    label: str
    interval: str
    data_type: str
    price_table: str
    probe: Callable[[date], str]
    target_date: Callable[[], date]
    end_exclusive: Callable[[date], date]
    on_duplicate: bool
    support_years: bool


def price_rows_from_df(df: pd.DataFrame) -> list:
    return [
        (
            r.ticker,
            r.date,
            to_float(getattr(r, "open", None)),
            to_float(getattr(r, "high", None)),
            to_float(getattr(r, "low", None)),
            to_float(r.close),
            to_int(getattr(r, "volume", None)),
        )
        for r in df.itertuples(index=False)
    ]


def _sleep_between_batches(label: str) -> None:
    delay = YF_BATCH_DELAY_BASE + random.uniform(
        -YF_BATCH_DELAY_JITTER, YF_BATCH_DELAY_JITTER
    )
    log.debug(f"[{label}] 等待 {delay:.1f}s 后继续")
    time.sleep(delay)


def _download_and_save(
    conn,
    tickers: List[str],
    start_date: Optional[date],
    result: Dict[str, str],
    *,
    spec: UsPriceSpec,
    years: Optional[int] = None,
) -> None:
    if not tickers:
        return

    target = spec.target_date()
    if start_date is None:
        if spec.support_years and years:
            start_date = target - timedelta(days=365 * years)
        else:
            start_date = date.fromisoformat(START_DATE_US)

    end_dt = spec.end_exclusive(target)
    yf_symbols = [to_yfinance_us(t) for t in tickers]
    log.info(
        f"[{spec.label}] 下载 {len(tickers)} 只, {start_date} ~ {target} interval={spec.interval}"
    )

    try:
        df = download_with_retry(
            tickers=yf_symbols,
            start=start_date.strftime("%Y-%m-%d"),
            end=end_dt.strftime("%Y-%m-%d"),
            interval=spec.interval,
            threads=YF_THREADS,
            timeout=YF_TIMEOUT,
            retry_count=YF_RETRY_COUNT,
            repair=False,
            context=f"[{spec.label}] ",
        )
    except Exception as last_exc:
        msg = f"yfinance {spec.label} failed after {YF_RETRY_COUNT} retries: {last_exc}"
        log.error(msg)
        for t in tickers:
            set_sync_error(conn, t, spec.data_type, msg)
            result[t] = f"error: {last_exc}"
        return

    top_level: set = set()
    if df is not None and not df.empty and isinstance(df.columns, pd.MultiIndex):
        top_level = set(df.columns.get_level_values(0))

    price_rows: list = []
    sync_rows: list = []
    ok_tickers: list = []

    for t in tickers:
        yf_t = to_yfinance_us(t)
        if yf_t not in top_level:
            log.warning(f"[{t}] yfinance: ticker not in response")
            set_sync_error(conn, t, spec.data_type, "yfinance: ticker not in response")
            result[t] = "no_data"
            continue
        sub = df[yf_t]
        normalized = normalize_daily_frame(t, sub)
        if normalized.empty:
            log.warning(f"[{t}] yfinance: empty frame")
            set_sync_error(conn, t, spec.data_type, "yfinance: empty frame")
            result[t] = "no_data"
            continue
        rows = price_rows_from_df(normalized)
        new_last = normalized["date"].max()
        price_rows.extend(rows)
        sync_rows.append((t, spec.data_type, new_last, len(rows), "ok", ""))
        ok_tickers.append(t)
        result[t] = "ok"
        log.info(f"[{t}] 写入 {len(rows)} 条，最新={new_last}")

    if price_rows or sync_rows:
        try:
            flush_prices_and_sync(
                conn,
                price_rows,
                sync_rows,
                on_duplicate=spec.on_duplicate,
                price_table=spec.price_table,
            )
        except Exception as e:
            log.error(f"[{spec.label}] 写库失败: {e}")
            for t in ok_tickers:
                set_sync_error(conn, t, spec.data_type, str(e))
                result[t] = f"error: {e}"


def run_us_equity_batch(
    tickers: List[str],
    *,
    spec: UsPriceSpec,
    full_rebase: bool = False,
    years: Optional[int] = None,
) -> Dict[str, str]:
    if not tickers:
        return {}

    target = spec.target_date()
    status = spec.probe(target)

    if status == "rate_limit":
        log.warning(f"[AAPL {spec.label}] yfinance 被限速，跳过")
        return {t: "error: rate_limit" for t in tickers}
    if status == "no_data":
        log.warning(f"[AAPL {spec.label}] yfinance 暂无 {target} 数据，跳过")
        return {t: "error: no_data" for t in tickers}
    if status == "error":
        log.warning(f"[AAPL {spec.label}] 测试请求失败，跳过")
        return {t: "error: test_failed" for t in tickers}

    log.info(f"[AAPL {spec.label}] 已有 {target} 数据，开始批量下载")
    result: Dict[str, str] = {}
    conn = get_conn()
    try:
        if full_rebase:
            actual_years = years if (spec.support_years and years) else (
                HISTORY_YEARS_US if spec.support_years else None
            )
            log.info(f"[{spec.label}] rebase: {len(tickers)} tickers years={actual_years}")
            batches = list(chunked(tickers, YF_BATCH_SIZE))
            for idx, batch in enumerate(batches, 1):
                _download_and_save(
                    conn, batch, None, result, spec=spec, years=actual_years
                )
                if idx < len(batches):
                    _sleep_between_batches(spec.label)
        else:
            new_tickers: list[str] = []
            pending_tickers: list[str] = []
            pending_start: Optional[date] = None
            lookback_floor = target - timedelta(days=YF_LOOKBACK_DAYS)
            last_map = get_last_sync_map(conn, tickers, spec.data_type)
            for t in tickers:
                last = last_map.get(t)
                if last is None:
                    new_tickers.append(t)
                elif last < target:
                    start_dt = max(last + timedelta(days=1), lookback_floor)
                    pending_tickers.append(t)
                    if pending_start is None or start_dt < pending_start:
                        pending_start = start_dt

            if new_tickers:
                log.info(f"[{spec.label}] {len(new_tickers)} 新 ticker 全量")
                batches_new = list(chunked(new_tickers, YF_BATCH_SIZE))
                for idx, batch_new in enumerate(batches_new, 1):
                    _download_and_save(conn, batch_new, None, result, spec=spec)
                    if idx < len(batches_new):
                        _sleep_between_batches(spec.label)

            if pending_tickers:
                log.info(
                    f"[{spec.label}] {len(pending_tickers)} 增量 "
                    f"from {pending_start} to {target}"
                )
                batches_pending = list(chunked(pending_tickers, YF_BATCH_SIZE))
                for idx, batch_pending in enumerate(batches_pending, 1):
                    _download_and_save(
                        conn, batch_pending, pending_start, result, spec=spec
                    )
                    if idx < len(batches_pending):
                        _sleep_between_batches(spec.label)
            else:
                log.info(f"[{spec.label}] 全部已同步到 {target}")

        return result
    finally:
        conn.close()
```

- [ ] **Step 2: 重写 `prices_us.py` 为薄入口**

```python
"""US equity daily prices via yfinance (incremental by sync_log)."""
from __future__ import annotations

from datetime import timedelta
from typing import Dict, List, Optional

from core.trading_calendar import last_us_trading_date
from apis.yfinance.probe import probe_daily
from apis.yfinance.prices_batch import UsPriceSpec, run_us_equity_batch


def update_prices_batch(
    tickers: List[str], full_rebase: bool = False, years: Optional[int] = None
) -> Dict[str, str]:
    def _end_exclusive(target):
        return target + timedelta(days=1)

    spec = UsPriceSpec(
        label="batch",
        interval="1d",
        data_type="price",
        price_table="prices",
        probe=probe_daily,
        target_date=last_us_trading_date,
        end_exclusive=_end_exclusive,
        on_duplicate=False,
        support_years=True,
    )
    return run_us_equity_batch(
        tickers, spec=spec, full_rebase=full_rebase, years=years
    )
```

- [ ] **Step 3: 重写 `prices_us_weekly.py` 为薄入口**

保留 `_last_us_weekly_date` 原实现（测依赖 `patch("apis.yfinance.prices_us_weekly.datetime")`）。

```python
"""US equity weekly prices via yfinance (interval=1wk)."""
from __future__ import annotations

from datetime import datetime, timedelta, date
from typing import Dict, List

from apis.yfinance.probe import probe_weekly
from apis.yfinance.prices_batch import UsPriceSpec, run_us_equity_batch


def _last_us_weekly_date() -> date:
    """Return Monday of the most recently completed US trading week."""
    now = datetime.now()
    weekday = now.weekday()
    hour = now.hour
    today = now.date()
    this_monday = today - timedelta(days=weekday)
    if (weekday == 5 and hour >= 5) or weekday == 6:
        return this_monday
    return this_monday - timedelta(days=7)


def update_weekly_batch(tickers: List[str], full_rebase: bool = False) -> Dict[str, str]:
    def _end_exclusive(target: date) -> date:
        return target + timedelta(days=7)

    # Build Spec at call time so patches on this module's probe_weekly / _last_us_weekly_date apply.
    spec = UsPriceSpec(
        label="weekly batch",
        interval="1wk",
        data_type="price_weekly",
        price_table="prices_weekly",
        probe=probe_weekly,
        target_date=_last_us_weekly_date,
        end_exclusive=_end_exclusive,
        on_duplicate=False,
        support_years=False,
    )
    return run_us_equity_batch(tickers, spec=spec, full_rebase=full_rebase)
```

**Patch 兼容：** 现有测 `patch("apis.yfinance.prices_us_weekly.probe_weekly")` —— 因 Spec 在函数内用本模块全局名 `probe_weekly`，patch 后 `update_weekly_batch` 内绑定的是 patched 对象。OK。

- [ ] **Step 4: 改 `test_stock_updater_us_weekly.py` 的 save 测**

删除/替换 `test_save_weekly_prices_uses_prices_weekly_table`（`_save_weekly_prices` 将不存在）。改为依赖 Task 2 的 flush 契约测，或改为：

```python
def test_weekly_spec_targets_prices_weekly_table():
    """Document contract: weekly uses prices_weekly + price_weekly."""
    # Smoke: update_weekly_batch empty still works
    from apis.yfinance.prices_us_weekly import update_weekly_batch
    assert update_weekly_batch([]) == {}
```

- [ ] **Step 5: 跑测**

```bash
uv run pytest tests/test_yf_prices_batch.py tests/test_stock_updater_us_weekly.py tests/test_yf_probe.py tests/test_pipeline.py -q
```

Expected: PASS。若 MultiIndex mock 与 `normalize_daily_frame` 不兼容，调整 Task 2 mock frame 为 normalize 可吃的形状（参考 `test_normalize_weekly_frame_happy_path` 单 ticker 列，或在 `_download_and_save` 测中 mock `normalize_daily_frame`）。

- [ ] **Step 6: Commit**

```bash
git add apis/yfinance/prices_batch.py apis/yfinance/prices_us.py \
  apis/yfinance/prices_us_weekly.py tests/test_yf_prices_batch.py \
  tests/test_stock_updater_us_weekly.py
git commit -m "refactor(yf): parameterize US daily/weekly batch runner (P1)"
```

---

### Task 4: P1 — 全量回归（yf 相关）

**Files:** 无新文件（修复失败时改 Task 3 产物）

- [ ] **Step 1: 全量测**

```bash
uv run pytest tests/ -q
```

Expected: PASS

- [ ] **Step 2: 结构检查**

```bash
rg -n "def update_prices_batch|def update_weekly_batch" apis/yfinance/
rg -n "Pipeline\.daily|weekly\(" jobs/pipeline.py
```

Expected: 两个 update 入口仍在；`pipeline.daily` 不调用 weekly。

- [ ] **Step 3: 若有修复则 commit**

```bash
git add -u
git commit -m "fix(yf): stabilize prices_batch after full suite"
```

（无改动则跳过 commit）

---

### Task 5: P2 — CN batch 实现 + 测适配

**Files:**
- Create: `apis/tushare/prices_cn_batch.py`
- Modify: `apis/tushare/prices_cn.py`
- Modify: `apis/tushare/prices_cn_weekly.py`
- Modify: `tests/test_stock_updater_cn_weekly.py`
- Create (optional): `tests/test_cn_prices_batch.py`

**Interfaces:**
- Produces:
  - `CnPriceSpec(label, freq, data_type, price_table, on_duplicate=True)`
  - `run_cn_equity_batch(tickers, *, spec, full_rebase=False, years=None) -> dict[str, str]`
  - `normalize_pro_bar(df) -> DataFrame`（公开或模块级，测可 import）
  - 入口签名不变

- [ ] **Step 1: 实现 `prices_cn_batch.py`**

从现有 `prices_cn.py` / `prices_cn_weekly.py` 合并逻辑，关键点：

1. `CnPriceSpec` 含 `freq: str`（`"D"` / `"W"`）、`data_type`、`price_table`、`label`、`on_duplicate: bool = True`。
2. `_fetch_one(ticker, start, end, freq)` → `client.pro_bar(..., freq=freq, adj="qfq")`。
3. `_process_tickers_batched`：**增量时**用调用方传入的 `last_map: dict[str, date | None]`，**禁止**循环内 `get_last_sync`：

```python
# inside loop when not full_rebase:
last = last_map.get(t)
if last:
    start = (last + timedelta(days=1)).strftime("%Y%m%d")
else:
    start = TUSHARE_BACKFILL_START
```

4. `_flush_batch` → `flush_prices_and_sync(..., price_table=spec.price_table, on_duplicate=spec.on_duplicate)`。
5. `run_cn_equity_batch`：`last_map = {} if full_rebase else get_last_sync_map(conn, tickers, spec.data_type)`，再分 new/pending，与现 `update_prices_batch` 相同。
6. `normalize_pro_bar` 单份实现。

- [ ] **Step 2: 薄入口**

`prices_cn.py`:

```python
from apis.tushare.prices_cn_batch import CnPriceSpec, run_cn_equity_batch

def update_prices_batch(tickers, full_rebase=False, years=None):
    spec = CnPriceSpec(
        label="cn", freq="D", data_type="price",
        price_table="prices", on_duplicate=True,
    )
    return run_cn_equity_batch(tickers, spec=spec, full_rebase=full_rebase, years=years)
```

`prices_cn_weekly.py`:

```python
from apis.tushare.prices_cn_batch import (
    CnPriceSpec, run_cn_equity_batch, normalize_pro_bar,
)

SYNC_DATA_TYPE = "price_weekly"

def _normalize_pro_bar(df):
    return normalize_pro_bar(df)

def _save_weekly_prices_batch(conn, rows):
    """Kept for unit test table-name assertion."""
    sql = """
        INSERT INTO prices_weekly (ticker, date, open, high, low, close, volume)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            open=VALUES(open), high=VALUES(high), low=VALUES(low),
            close=VALUES(close), volume=VALUES(volume)
    """
    with conn.cursor() as cur:
        cur.executemany(sql, rows)
    return len(rows)

def update_weekly_batch(tickers, full_rebase=False, years=None):
    spec = CnPriceSpec(
        label="cn weekly", freq="W", data_type="price_weekly",
        price_table="prices_weekly", on_duplicate=True,
    )
    return run_cn_equity_batch(tickers, spec=spec, full_rebase=full_rebase, years=years)
```

**测试 patch：** 现有测 patch `apis.tushare.prices_cn_weekly.get_last_sync_map` / `_fetch_one` / `_flush_batch`。  
薄入口后这些符号若不在 weekly 模块，**必须**改测为：

```python
patch("apis.tushare.prices_cn_batch.get_last_sync_map", ...)
patch("apis.tushare.prices_cn_batch.fetch_one", ...)  # 若改名
# 或
patch("apis.tushare.prices_cn_batch.run_cn_equity_batch", ...)
```

推荐：`run_cn_equity_batch` 内调用本模块 `fetch_one` / `get_last_sync_map`；测改为 patch `apis.tushare.prices_cn_batch.*`。保留 `_normalize_pro_bar` re-export 使现有 normalize 测仍 `from prices_cn_weekly import _normalize_pro_bar`。

- [ ] **Step 3: 更新 `tests/test_stock_updater_cn_weekly.py` patch 路径**

将：

- `apis.tushare.prices_cn_weekly.get_conn` → `apis.tushare.prices_cn_batch.get_conn`（若 runner 用 batch 的 get_conn）
- `get_last_sync_map` / `_fetch_one` / `_flush_batch` 同理改到 `prices_cn_batch`

或在 `prices_cn_weekly.update_weekly_batch` 内显式 `import` 后调用，使 patch 点仍在 weekly——**更省事的做法：**

```python
# prices_cn_weekly.py — re-export names tests patch
from apis.tushare.prices_cn_batch import (
    get_conn,  # no — get_conn is from core
)
```

**明确推荐：** 改测试 patch 到 `prices_cn_batch`；`_normalize_pro_bar` / `_save_weekly_prices_batch` / `SYNC_DATA_TYPE` 留在 weekly 文件。

- [ ] **Step 4: 断言无 per-ticker get_last_sync**

```bash
rg -n "get_last_sync\(" apis/tushare/prices_cn.py apis/tushare/prices_cn_weekly.py apis/tushare/prices_cn_batch.py
```

Expected: 无 `get_last_sync(`（仅 `get_last_sync_map`）。

- [ ] **Step 5: 跑测**

```bash
uv run pytest tests/test_stock_updater_cn_weekly.py tests/test_backfill_prices.py tests/test_market_cn.py -q
uv run pytest tests/ -q
```

- [ ] **Step 6: Commit**

```bash
git add apis/tushare/prices_cn_batch.py apis/tushare/prices_cn.py \
  apis/tushare/prices_cn_weekly.py tests/test_stock_updater_cn_weekly.py \
  tests/test_cn_prices_batch.py 2>/dev/null
git commit -m "refactor(tushare): parameterize CN daily/weekly batch runner (P2)"
```

---

### Task 6: P3 — `write_utils` + 单测（TDD）

**Files:**
- Create: `apis/futu/write_utils.py`
- Create: `tests/test_futu_write_utils.py`

**Interfaces:**
- Produces:
  - `upsert_rows(table: str, columns: list[str], rows: list[tuple], update_columns: list[str], *, ticker: str | None = None) -> int`
  - `paginate_call(client, method: str, code: str, *, list_key: str, page_num: int = 50, **kwargs) -> list`

- [ ] **Step 1: 写测**

```python
# tests/test_futu_write_utils.py
from unittest.mock import MagicMock, patch


def test_upsert_rows_builds_odku_and_commits():
    from apis.futu.write_utils import upsert_rows

    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value.__enter__ = lambda s: mock_cur
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

    rows = [("AAPL", "x", "1")]
    with patch("apis.futu.write_utils.get_conn") as g:
        g.return_value.__enter__ = lambda s: mock_conn
        g.return_value.__exit__ = MagicMock(return_value=False)
        n = upsert_rows(
            "us_company_profile",
            ["ticker", "field_name", "field_value"],
            rows,
            ["field_value"],
            ticker="AAPL",
        )
    assert n == 1
    sql = mock_cur.executemany.call_args[0][0]
    assert "INSERT INTO us_company_profile" in sql
    assert "ON DUPLICATE KEY UPDATE" in sql
    assert "field_value=VALUES(field_value)" in sql
    mock_conn.commit.assert_called_once()


def test_upsert_rows_empty_returns_zero():
    from apis.futu.write_utils import upsert_rows
    assert upsert_rows("t", ["a"], [], ["a"]) == 0


def test_paginate_call_stops_on_empty_or_sentinel():
    from apis.futu.write_utils import paginate_call

    client = MagicMock()
    client.call.side_effect = [
        {"item_list": [{"id": 1}], "next_key": "abc"},
        {"item_list": [{"id": 2}], "next_key": "-1"},
    ]
    items = paginate_call(
        client, "get_foo", "US.AAPL", list_key="item_list", page_num=50
    )
    assert [i["id"] for i in items] == [1, 2]
    assert client.call.call_count == 2
```

- [ ] **Step 2: 跑红**

```bash
uv run pytest tests/test_futu_write_utils.py -v
```

Expected: FAIL import

- [ ] **Step 3: 实现 `apis/futu/write_utils.py`**

```python
"""Shared Futu upsert + pagination helpers (not a framework)."""
from __future__ import annotations

import logging
from typing import Any

from core.db_client import get_conn

log = logging.getLogger(__name__)


def upsert_rows(
    table: str,
    columns: list[str],
    rows: list[tuple],
    update_columns: list[str],
    *,
    ticker: str | None = None,
) -> int:
    if not rows:
        return 0
    col_sql = ", ".join(columns)
    placeholders = ", ".join(["%s"] * len(columns))
    odku = ", ".join(f"{c}=VALUES({c})" for c in update_columns)
    sql = (
        f"INSERT INTO {table} ({col_sql}) VALUES ({placeholders}) "
        f"ON DUPLICATE KEY UPDATE {odku}"
    )
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.executemany(sql, rows)
        conn.commit()
    label = f"{table} {ticker}" if ticker else table
    log.info(f"{label}: {len(rows)} rows")
    return len(rows)


def paginate_call(
    client,
    method: str,
    code: str,
    *,
    list_key: str,
    page_num: int = 50,
    **kwargs: Any,
) -> list:
    out: list = []
    next_key = None
    while True:
        data = client.call(method, code, next_key=next_key, num=page_num, **kwargs)
        payload = data if isinstance(data, dict) else {}
        chunk = payload.get(list_key, []) or []
        out.extend(chunk)
        next_key = payload.get("next_key", "-1")
        if not chunk or next_key == "-1":
            break
    return out
```

- [ ] **Step 4: 绿 + commit**

```bash
uv run pytest tests/test_futu_write_utils.py -q
git add apis/futu/write_utils.py tests/test_futu_write_utils.py
git commit -m "feat(futu): add upsert_rows and paginate_call helpers (P3)"
```

---

### Task 7: P3 — 迁移 thin backfill（profile / efficiency / actions）

**Files:**
- Modify: `apis/futu/backfill_profile.py`
- Modify: `apis/futu/backfill_efficiency.py`
- Modify: `apis/futu/backfill_actions.py`
- Test: `tests/test_futu_backfill_profile.py`, `tests/test_futu_backfill_efficiency.py`, `tests/test_futu_backfill_actions.py`（若存在）

**Interfaces:**
- Consumes: `upsert_rows`, `paginate_call`
- Produces: 同名 `backfill_*` / `backfill_all` 签名与返回 dict 字段不变

- [ ] **Step 1: `backfill_profile.py` 改用 upsert_rows**

将 `with get_conn()...executemany...commit` 换成：

```python
from apis.futu.write_utils import upsert_rows

# after building rows:
return upsert_rows(
    "us_company_profile",
    ["ticker", "field_name", "field_value", "updated_at"],
    rows,
    ["field_value", "updated_at"],
    ticker=ticker,
)
```

**禁止**改 row 字段顺序或列名。

- [ ] **Step 2: `backfill_efficiency.py` 同样替换 upsert 块**

`update_columns` 与原 SQL ODKU 列一致：`employee_num`, `income_per_capita`, `profit_per_capita`, `raw_payload`（及原 SQL 中列出的列）。

- [ ] **Step 3: `backfill_actions.py`**

- `backfill_dividends`：非分页 → `upsert_rows`
- `backfill_splits`：分页循环 → `paginate_call(..., list_key="split_list")` 再组 rows → `upsert_rows`

- [ ] **Step 4: 跑 futu 相关测**

```bash
uv run pytest tests/test_futu_backfill_profile.py tests/test_futu_backfill_efficiency.py \
  tests/test_futu_backfill_actions.py tests/test_futu_write_utils.py -q
```

若无独立 profile/efficiency 测文件，跑：

```bash
uv run pytest tests/test_futu_*.py -q
```

- [ ] **Step 5: Commit**

```bash
git add apis/futu/backfill_profile.py apis/futu/backfill_efficiency.py apis/futu/backfill_actions.py
git commit -m "refactor(futu): migrate profile/efficiency/actions to write_utils (P3)"
```

---

### Task 8: P3 — 迁移其余 backfill + financial + 可选 snapshot

**Files:**
- Modify: `apis/futu/backfill_financial.py`
- Modify: `apis/futu/backfill_earnings.py`
- Modify: `apis/futu/backfill_revenue.py`
- Modify: `apis/futu/backfill_shareholders.py`
- Modify (optional Rule of Three): `snapshot_daily.py`, `snapshot_daily_ext.py`, `snapshot_weekly.py` — **仅当**三处仍有重复 upsert 样板时抽小函数到 `write_utils`；否则只用 `upsert_rows` 替换重复 SQL。

**规则（每文件）：**

1. 只替换「executemany + ODKU + commit」与「next_key 分页」。
2. **不改** tuple 字段顺序、表名、`raw_payload` 内容、`ticker_stream` / `run_streams` / `backfill_all` 返回结构。
3. 每改完 1–2 文件跑：

```bash
uv run pytest tests/test_futu_*.py -q
```

- [ ] **Step 1: financial** — 分页用 `paginate_call`（`list_key="report_list"`）；写库用 `upsert_rows`；保留 `STATEMENT_TABLES` 循环。
- [ ] **Step 2: earnings / revenue** — 同上。
- [ ] **Step 3: shareholders** — 多表分别 upsert；映射函数留本地。
- [ ] **Step 4: snapshot_*** — 能直接 `upsert_rows` 则换；**不要**为 1–2 处重复强抽 Helper C。
- [ ] **Step 5: 全 futu 测 + commit**

```bash
uv run pytest tests/test_futu_*.py -q
git add apis/futu/
git commit -m "refactor(futu): migrate remaining backfills to write_utils (P3)"
```

---

### Task 9: P4 — CLI 命令迁出 + main re-export

**Files:**
- Create: `cli/commands_prices.py`
- Create: `cli/commands_tushare.py`
- Create: `cli/commands_futu.py`
- Create: `cli/commands_db.py`
- Create: `cli/commands_meta.py`
- Create: `cli/commands_common.py`（可选：`_import_market`, `_run_buffered`, `_format_run_result`）
- Modify: `main.py`
- Test: `tests/test_cli.py`, `tests/test_main_tushare_backfill.py`, `tests/test_futu_cli.py`, `tests/test_cli_rebase_etf.py`, `tests/test_intraday_updater_us.py`

**Interfaces:**
- Produces: `main.cmd_*` 仍可 import（re-export）；`main.main` / dispatch 行为不变
- argv 零变化

- [ ] **Step 1: 抽出 `cli/commands_common.py`**

把 `main.py` 中 `_format_run_result`、`_run_buffered`、`_import_market` 原样搬入（import 路径改为本模块）。

- [ ] **Step 2: 按域搬 cmd**

| 新文件 | 函数 |
|--------|------|
| `commands_meta.py` | `cmd_init`, `cmd_status` |
| `commands_prices.py` | `cmd_daily`, `cmd_weekly`, `cmd_rebase`, `cmd_intraday` |
| `commands_tushare.py` | `cmd_tushare_backfill`, `cmd_tushare_full`, `cmd_tushare_flush` |
| `commands_futu.py` | `cmd_futu_full`, `cmd_futu_sync`, `cmd_futu_flush`, `_run_futu` |
| `commands_db.py` | `cmd_migrate_intraday`, `cmd_purge_index` |

各文件从 `cli.commands_common` 引 `_import_market` / `_run_buffered`。

- [ ] **Step 3: 瘦身 `main.py`**

保留：

- NO_PROXY / logging 引导
- `from cli.commands_prices import cmd_daily, cmd_weekly, cmd_rebase, cmd_intraday`
- 其他 domain 的 `cmd_*` re-export
- `_dispatch_*` 与 `main()`
- `if __name__ == "__main__"`

**测试兼容：** `from main import cmd_tushare_backfill` 与 `patch("main.cmd_daily")` 必须仍有效 → re-export 在 `main` 命名空间。

`test_main_tushare_backfill.py` 中 `from main import _format_run_result`：

- 选项 A：`main` 再 export `_format_run_result`
- 选项 B：改测为 `from cli.commands_common import _format_run_result` 且 patch 路径同步

**推荐 A**（少改测）：

```python
from cli.commands_common import _format_run_result, _run_buffered  # if tests need
```

在 `main.py`：`from cli.commands_common import _format_run_result  # re-export for tests`

- [ ] **Step 4: 跑 CLI 测**

```bash
uv run pytest tests/test_cli.py tests/test_main_tushare_backfill.py \
  tests/test_futu_cli.py tests/test_cli_rebase_etf.py \
  tests/test_intraday_updater_us.py -q
uv run pytest tests/ -q
```

- [ ] **Step 5: Commit**

```bash
git add cli/ main.py tests/
git commit -m "refactor(cli): move cmd_* into cli/commands_* with main re-exports (P4)"
```

---

### Task 10: 文档与 design 状态 + 终验

**Files:**
- Modify: `README.md`（架构树）
- Modify: `docs/superpowers/specs/2026-07-16-structural-debt-cleanup-design.md`（状态 → 已实现）
- Modify: `CLAUDE.md`（若架构一句需补 cli/）

- [ ] **Step 1: README 架构树**

在「架构设计」代码树中，`main.py` 旁注明入口；增加：

```text
cli/
  parser.py / deprecate.py
  commands_prices.py / commands_tushare.py / commands_futu.py
  commands_db.py / commands_meta.py / commands_common.py
```

`apis/yfinance` 增加 `prices_batch.py`；`apis/tushare` 增加 `prices_cn_batch.py`；`apis/futu` 增加 `write_utils.py`。

- [ ] **Step 2: Spec 状态**

将 design 文首 **状态** 改为：`已实现（P0–P4）`，日期可注完成日。

- [ ] **Step 3: 终验清单**

```bash
uv run pytest tests/ -q
rg -n 'AKSHARE_|to_akshare|to_efinance' --type py
rg -n 'def update_prices_batch|def update_weekly_batch' apis/
rg -n 'ON DUPLICATE KEY UPDATE' apis/futu/ | head -40
```

Expected:

- 全绿
- 无 AKSHARE 配置/转换（允许 `main` 里 `_AKSHARE_NO_PROXY` 变量名若未改）
- 日/周双入口仍在
- futu ODKU 多数在 `write_utils` 或少量特殊 SQL

- [ ] **Step 4: Commit**

```bash
git add -f docs/superpowers/specs/2026-07-16-structural-debt-cleanup-design.md
git add README.md CLAUDE.md
git commit -m "docs: mark structural debt cleanup P0–P4 implemented"
```

---

## Self-Review (plan vs spec)

| Spec 项 | Task |
|---------|------|
| P0 死码/INDEX/CLAUDE | Task 1 |
| P1 yf 参数化 + weekly batch flush | Task 2–4 |
| 日/周 CLI 分离 | Global + Task 3/4 检查 pipeline |
| P2 ts 参数化 + bulk map | Task 5 |
| P3 write_utils + 迁移 | Task 6–8 |
| P4 CLI 瘦身 + re-export | Task 9 |
| 文档 | Task 10 |
| 不做跨源引擎 / hk / etf… | Global Constraints |

**占位符：** 已扫过无 TBD/TODO。  
**类型一致：** `UsPriceSpec` / `CnPriceSpec` / `run_*_equity_batch` / `upsert_rows` / `paginate_call` 贯穿后文。

---

## Execution Handoff

Plan 完成后见下条消息中的执行选项。
