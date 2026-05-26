# CN Sector ETF Price Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add daily hfq close ingest for 17 A-share sector/theme ETFs into `index_prices` table, enabling CN-vs-US sector trend comparison.

**Architecture:** New `data/etf_updater_cn.py` module fetches `fund_daily × fund_adj` via tushare client and writes hfq close to `index_prices` using ts_code as `index_id`. Hooked into `market_cn.update_index_price()` so existing `daily --market cn` pipeline auto-picks it up. New `rebase --etf-only` CLI flag for full re-pull.

**Tech Stack:** Python 3.12, pandas, tushare, MariaDB, pytest, uv.

**Spec:** `docs/superpowers/specs/2026-05-26-cn-sector-etf-price-design.md`

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `config.py` | Modify | Add `CN_SECTOR_ETFS` dict (ts_code → name, gics) |
| `data/etf_updater_cn.py` | Create | `fetch_etf_daily_hfq()` + `update_etf_prices()` |
| `data/market_cn.py` | Modify | Hook `update_etf_prices()` into `update_index_price()` |
| `main.py` | Modify | Add `rebase --etf-only` flag + dispatch |
| `tests/test_etf_updater_cn.py` | Create | Unit tests for fetch + update |
| `tests/test_config.py` | Modify | Verify GICS 11-class coverage |
| `tests/test_market_cn_etf_hook.py` | Create | Verify ETF hook in `update_index_price()` |
| `scripts/verify_cn_etfs.py` | Create | One-shot ts_code existence check against `fund_basic` |
| `README.md` | Modify | Add CN ETF query examples |

---

## Task 1: Add `CN_SECTOR_ETFS` config

**Files:**
- Modify: `config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_config.py`:

```python
def test_cn_sector_etfs_covers_gics_11():
    """CN_SECTOR_ETFS must cover all 11 GICS sectors plus themes."""
    from config import CN_SECTOR_ETFS

    assert len(CN_SECTOR_ETFS) >= 11, "must cover at least 11 sectors"

    # Every entry has name + gics fields
    for ts_code, meta in CN_SECTOR_ETFS.items():
        assert "." in ts_code and ts_code.endswith((".SH", ".SZ")), f"bad ts_code {ts_code}"
        assert "name" in meta and meta["name"], f"missing name for {ts_code}"
        assert "gics" in meta and meta["gics"], f"missing gics for {ts_code}"

    # GICS 11 sectors all present
    gics_values = {meta["gics"] for meta in CN_SECTOR_ETFS.values()}
    required_gics = {
        "Energy", "Materials", "Industrials",
        "ConsumerDiscretionary", "ConsumerStaples", "HealthCare",
        "Financials", "InformationTechnology", "CommunicationServices",
        "Utilities", "RealEstate",
    }
    missing = required_gics - gics_values
    assert not missing, f"missing GICS sectors: {missing}"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_config.py::test_cn_sector_etfs_covers_gics_11 -v
```

Expected: FAIL with `ImportError` or `AttributeError` (no `CN_SECTOR_ETFS`).

- [ ] **Step 3: Add config dict**

Append to `config.py` (after `INDEX_DELAY = 2.0`):

```python
# A-share 行业 ETF (后复权日线 via tushare fund_daily × fund_adj)
# 与 US XL* 对齐 GICS 11 类 + A 股特色主题
CN_SECTOR_ETFS = {
    "515220.SH": {"name": "煤炭ETF",     "gics": "Energy"},
    "512400.SH": {"name": "有色金属ETF", "gics": "Materials"},
    "512660.SH": {"name": "军工ETF",     "gics": "Industrials"},
    "159996.SZ": {"name": "家电ETF",     "gics": "ConsumerDiscretionary"},
    "512690.SH": {"name": "酒ETF",       "gics": "ConsumerStaples"},
    "512170.SH": {"name": "医疗ETF",     "gics": "HealthCare"},
    "512010.SH": {"name": "医药ETF",     "gics": "HealthCare"},
    "512800.SH": {"name": "银行ETF",     "gics": "Financials"},
    "512000.SH": {"name": "券商ETF",     "gics": "Financials"},
    "512720.SH": {"name": "计算机ETF",   "gics": "InformationTechnology"},
    "512480.SH": {"name": "半导体ETF",   "gics": "InformationTechnology"},
    "515050.SH": {"name": "5G通信ETF",   "gics": "CommunicationServices"},
    "159611.SZ": {"name": "电力ETF",     "gics": "Utilities"},
    "512200.SH": {"name": "房地产ETF",   "gics": "RealEstate"},
    "515790.SH": {"name": "光伏ETF",     "gics": "Theme.Solar"},
    "515030.SH": {"name": "新能源车ETF", "gics": "Theme.NEV"},
    "159995.SZ": {"name": "芯片ETF",     "gics": "Theme.Chip"},
}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/test_config.py::test_cn_sector_etfs_covers_gics_11 -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add config.py tests/test_config.py
git commit -m "feat: add CN_SECTOR_ETFS config for A-share sector/theme ETFs"
```

---

## Task 2: Verify ts_code existence script

**Files:**
- Create: `scripts/verify_cn_etfs.py`

- [ ] **Step 1: Write script**

```python
"""一次性验证 CN_SECTOR_ETFS 中所有 ts_code 在 tushare fund_basic 存在。

跑法: uv run python scripts/verify_cn_etfs.py
"""
from config import CN_SECTOR_ETFS
from ts_ingest.client import get_client


def main() -> int:
    client = get_client()
    codes = list(CN_SECTOR_ETFS.keys())
    basic = client.call("fund_basic", market="E")
    if basic.empty:
        print("ERROR: fund_basic returned empty")
        return 1
    existing = set(basic["ts_code"].values)
    missing = [c for c in codes if c not in existing]
    if missing:
        print(f"MISSING {len(missing)}/{len(codes)}: {missing}")
        return 1
    print(f"OK: 全部 {len(codes)} 只 ETF 存在")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
```

- [ ] **Step 2: Run script**

```bash
uv run python scripts/verify_cn_etfs.py
```

Expected: `OK: 全部 17 只 ETF 存在`.

If any MISSING reported, fix `config.CN_SECTOR_ETFS` ts_code (look up correct code via tushare fund_basic web UI or query `client.call("fund_basic", market="E")` and grep by 中文 name).

- [ ] **Step 3: Commit**

```bash
git add scripts/verify_cn_etfs.py
git commit -m "chore: add one-shot script to verify CN ETF ts_codes"
```

---

## Task 3: `fetch_etf_daily_hfq` — merge `fund_daily × fund_adj`

**Files:**
- Create: `data/etf_updater_cn.py`
- Test: `tests/test_etf_updater_cn.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_etf_updater_cn.py`:

```python
"""Tests for CN sector ETF hfq close fetching via tushare."""
import pytest
from unittest.mock import patch, MagicMock
import pandas as pd
from datetime import date


@patch("data.etf_updater_cn.get_client")
def test_fetch_etf_daily_hfq_merges_close_and_adj(mock_get_client):
    """hfq_close = raw close × adj_factor, merged on trade_date."""
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client

    daily_df = pd.DataFrame({
        "ts_code": ["512800.SH", "512800.SH"],
        "trade_date": ["20260513", "20260512"],
        "close": [1.500, 1.480],
    })
    adj_df = pd.DataFrame({
        "ts_code": ["512800.SH", "512800.SH"],
        "trade_date": ["20260513", "20260512"],
        "adj_factor": [1.20, 1.20],
    })

    def fake_call(api, **kwargs):
        if api == "fund_daily":
            return daily_df
        if api == "fund_adj":
            return adj_df
        raise AssertionError(f"unexpected api: {api}")

    mock_client.call.side_effect = fake_call

    from data.etf_updater_cn import fetch_etf_daily_hfq
    df = fetch_etf_daily_hfq("512800.SH", start_date=None)

    assert list(df.columns) == ["date", "hfq_close"]
    assert len(df) == 2
    # Sorted ascending by date
    assert df.iloc[0]["date"] == date(2026, 5, 12)
    assert df.iloc[0]["hfq_close"] == pytest.approx(1.480 * 1.20)
    assert df.iloc[1]["date"] == date(2026, 5, 13)
    assert df.iloc[1]["hfq_close"] == pytest.approx(1.500 * 1.20)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_etf_updater_cn.py::test_fetch_etf_daily_hfq_merges_close_and_adj -v
```

Expected: FAIL with `ModuleNotFoundError: data.etf_updater_cn`.

- [ ] **Step 3: Create module with `fetch_etf_daily_hfq`**

Create `data/etf_updater_cn.py`:

```python
"""A-share 行业 ETF 后复权日线采集 via tushare fund_daily × fund_adj。

写入 index_prices 表，index_id 使用 ts_code（如 "512800.SH"）。
"""
from __future__ import annotations

import logging
from typing import Optional

import pandas as pd

from db import query, execute
from data.base import to_float
from ts_ingest.client import get_client
from config import CN_SECTOR_ETFS

log = logging.getLogger(__name__)


def fetch_etf_daily_hfq(ts_code: str, start_date: Optional[str]) -> pd.DataFrame:
    """拉取单只 ETF 后复权日线。

    Returns DataFrame[date, hfq_close]，按 date 升序。
    空 fund_daily 返回空 DataFrame。
    空 fund_adj 时 fallback raw close 并 warn。
    """
    client = get_client()

    daily = client.call("fund_daily", ts_code=ts_code, start_date=start_date)
    if daily is None or daily.empty:
        return pd.DataFrame()

    adj = client.call("fund_adj", ts_code=ts_code, start_date=start_date)

    if adj is None or adj.empty:
        log.warning(f"[{ts_code}] fund_adj 空，使用 raw close")
        df = daily[["trade_date", "close"]].copy()
        df["hfq_close"] = df["close"].astype(float)
    else:
        df = daily.merge(
            adj[["trade_date", "adj_factor"]],
            on="trade_date",
            how="left",
        )
        df = df.sort_values("trade_date")
        df["adj_factor"] = df["adj_factor"].ffill().bfill().fillna(1.0)
        df["hfq_close"] = df["close"].astype(float) * df["adj_factor"].astype(float)

    df["date"] = pd.to_datetime(df["trade_date"]).dt.date
    return df[["date", "hfq_close"]].sort_values("date").reset_index(drop=True)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/test_etf_updater_cn.py::test_fetch_etf_daily_hfq_merges_close_and_adj -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add data/etf_updater_cn.py tests/test_etf_updater_cn.py
git commit -m "feat: add fetch_etf_daily_hfq merging fund_daily × fund_adj"
```

---

## Task 4: `fetch_etf_daily_hfq` — edge cases

**Files:**
- Modify: `tests/test_etf_updater_cn.py`

- [ ] **Step 1: Write failing tests for empty/missing-adj/ffill cases**

Append to `tests/test_etf_updater_cn.py`:

```python
@patch("data.etf_updater_cn.get_client")
def test_fetch_etf_daily_hfq_empty_when_no_daily(mock_get_client):
    """Empty fund_daily → empty DataFrame, fund_adj not called."""
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    mock_client.call.return_value = pd.DataFrame()

    from data.etf_updater_cn import fetch_etf_daily_hfq
    df = fetch_etf_daily_hfq("512800.SH", start_date=None)

    assert df.empty
    # Only fund_daily called, not fund_adj (early return)
    assert mock_client.call.call_count == 1
    assert mock_client.call.call_args[0][0] == "fund_daily"


@patch("data.etf_updater_cn.get_client")
def test_fetch_etf_daily_hfq_handles_missing_adj(mock_get_client):
    """Empty fund_adj → fallback to raw close."""
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client

    daily_df = pd.DataFrame({
        "ts_code": ["512800.SH"],
        "trade_date": ["20260513"],
        "close": [1.500],
    })

    def fake_call(api, **kwargs):
        if api == "fund_daily":
            return daily_df
        if api == "fund_adj":
            return pd.DataFrame()
        raise AssertionError(api)

    mock_client.call.side_effect = fake_call

    from data.etf_updater_cn import fetch_etf_daily_hfq
    df = fetch_etf_daily_hfq("512800.SH", start_date=None)

    assert len(df) == 1
    assert df.iloc[0]["hfq_close"] == pytest.approx(1.500)


@patch("data.etf_updater_cn.get_client")
def test_fetch_etf_daily_hfq_ffill_adj_gaps(mock_get_client):
    """Missing adj_factor rows are forward-filled."""
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client

    daily_df = pd.DataFrame({
        "ts_code": ["512800.SH"] * 3,
        "trade_date": ["20260511", "20260512", "20260513"],
        "close": [1.0, 1.1, 1.2],
    })
    # adj only on 20260511 and 20260513, 20260512 missing
    adj_df = pd.DataFrame({
        "ts_code": ["512800.SH", "512800.SH"],
        "trade_date": ["20260511", "20260513"],
        "adj_factor": [2.0, 2.5],
    })

    def fake_call(api, **kwargs):
        if api == "fund_daily":
            return daily_df
        if api == "fund_adj":
            return adj_df
        raise AssertionError(api)

    mock_client.call.side_effect = fake_call

    from data.etf_updater_cn import fetch_etf_daily_hfq
    df = fetch_etf_daily_hfq("512800.SH", start_date=None)

    assert len(df) == 3
    # 20260512 ffills from 20260511 (factor 2.0)
    row_0512 = df[df["date"] == date(2026, 5, 12)].iloc[0]
    assert row_0512["hfq_close"] == pytest.approx(1.1 * 2.0)
```

- [ ] **Step 2: Run tests to verify behavior**

```bash
uv run pytest tests/test_etf_updater_cn.py -v
```

Expected: All 4 tests PASS (existing code already handles these cases via `ffill().bfill().fillna(1.0)` and early return).

If any fail, fix `fetch_etf_daily_hfq` until green.

- [ ] **Step 3: Commit**

```bash
git add tests/test_etf_updater_cn.py
git commit -m "test: cover empty/missing-adj/ffill edge cases in fetch_etf_daily_hfq"
```

---

## Task 5: `update_etf_prices` — incremental writer

**Files:**
- Modify: `data/etf_updater_cn.py`
- Modify: `tests/test_etf_updater_cn.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_etf_updater_cn.py`:

```python
@patch("data.etf_updater_cn.CN_SECTOR_ETFS", {"512800.SH": {"name": "银行ETF", "gics": "Financials"}})
@patch("data.etf_updater_cn.query")
@patch("data.etf_updater_cn.execute")
@patch("data.etf_updater_cn.fetch_etf_daily_hfq")
def test_update_etf_prices_writes_to_index_prices(mock_fetch, mock_execute, mock_query):
    """update_etf_prices writes (date, ts_code, hfq_close) rows to index_prices."""
    mock_query.return_value = [{"d": None}]  # no last_date
    mock_fetch.return_value = pd.DataFrame({
        "date": [date(2026, 5, 12), date(2026, 5, 13)],
        "hfq_close": [1.776, 1.800],
    })
    mock_execute.return_value = 2

    from data.etf_updater_cn import update_etf_prices
    total = update_etf_prices()

    assert total == 2
    # fetch called with start_date=20100101 (no last_date)
    mock_fetch.assert_called_once_with("512800.SH", start_date="20100101")

    # execute called with INSERT IGNORE into index_prices
    sql, rows = mock_execute.call_args[0]
    assert "INSERT IGNORE INTO index_prices" in sql
    assert rows == [
        (date(2026, 5, 12), "512800.SH", 1.776),
        (date(2026, 5, 13), "512800.SH", 1.800),
    ]


@patch("data.etf_updater_cn.CN_SECTOR_ETFS", {"512800.SH": {"name": "银行ETF", "gics": "Financials"}})
@patch("data.etf_updater_cn.query")
@patch("data.etf_updater_cn.execute")
@patch("data.etf_updater_cn.fetch_etf_daily_hfq")
def test_update_etf_prices_incremental_skips_existing(mock_fetch, mock_execute, mock_query):
    """last_date in DB → start_date passed as YYYYMMDD, rows ≤ last_date filtered."""
    mock_query.return_value = [{"d": date(2026, 5, 12)}]
    mock_fetch.return_value = pd.DataFrame({
        "date": [date(2026, 5, 12), date(2026, 5, 13)],
        "hfq_close": [1.776, 1.800],
    })
    mock_execute.return_value = 1

    from data.etf_updater_cn import update_etf_prices
    total = update_etf_prices()

    mock_fetch.assert_called_once_with("512800.SH", start_date="20260512")
    # Only 20260513 row written (20260512 == last_date filtered)
    rows = mock_execute.call_args[0][1]
    assert len(rows) == 1
    assert rows[0][0] == date(2026, 5, 13)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_etf_updater_cn.py::test_update_etf_prices_writes_to_index_prices tests/test_etf_updater_cn.py::test_update_etf_prices_incremental_skips_existing -v
```

Expected: FAIL with `AttributeError: module ... has no attribute 'update_etf_prices'`.

- [ ] **Step 3: Add `update_etf_prices` to `data/etf_updater_cn.py`**

Append to `data/etf_updater_cn.py`:

```python
def update_etf_prices(full_rebase: bool = False) -> int:
    """遍历 CN_SECTOR_ETFS，增量或全量写入 index_prices。

    full_rebase=True 时忽略 last_date，从 2010-01-01 全量重灌。
    单只 ETF 失败不阻断其他（log error 跳过）。
    """
    total = 0
    for ts_code, meta in CN_SECTOR_ETFS.items():
        try:
            if full_rebase:
                last_date = None
                start = "20100101"
            else:
                last = query(
                    "SELECT MAX(date) AS d FROM index_prices WHERE index_id=%s",
                    (ts_code,),
                )
                last_date = last[0]["d"] if last and last[0]["d"] else None
                start = last_date.strftime("%Y%m%d") if last_date else "20100101"

            df = fetch_etf_daily_hfq(ts_code, start_date=start)
            if df.empty:
                continue

            if last_date is not None:
                df = df[df["date"] > last_date]
            if df.empty:
                continue

            rows = [
                (r.date, ts_code, to_float(r.hfq_close))
                for r in df.itertuples(index=False)
            ]
            n = execute(
                "INSERT IGNORE INTO index_prices (date, index_id, close) VALUES (%s,%s,%s)",
                rows,
                many=True,
            )
            total += n
            log.info(f"[{ts_code}] {meta['name']} 写入 {n} 行")
        except Exception as e:
            log.error(f"[{ts_code}] 失败: {e}")
            continue
    return total
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_etf_updater_cn.py -v
```

Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add data/etf_updater_cn.py tests/test_etf_updater_cn.py
git commit -m "feat: add update_etf_prices incremental writer to index_prices"
```

---

## Task 6: `update_etf_prices` — failure isolation + full_rebase

**Files:**
- Modify: `tests/test_etf_updater_cn.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_etf_updater_cn.py`:

```python
@patch("data.etf_updater_cn.CN_SECTOR_ETFS", {
    "512800.SH": {"name": "银行ETF", "gics": "Financials"},
    "512000.SH": {"name": "券商ETF", "gics": "Financials"},
})
@patch("data.etf_updater_cn.query")
@patch("data.etf_updater_cn.execute")
@patch("data.etf_updater_cn.fetch_etf_daily_hfq")
def test_update_etf_prices_continues_on_single_failure(mock_fetch, mock_execute, mock_query):
    """If one ETF fetch raises, others still process."""
    mock_query.return_value = [{"d": None}]

    def fake_fetch(ts_code, start_date):
        if ts_code == "512800.SH":
            raise RuntimeError("tushare boom")
        return pd.DataFrame({
            "date": [date(2026, 5, 13)],
            "hfq_close": [1.0],
        })

    mock_fetch.side_effect = fake_fetch
    mock_execute.return_value = 1

    from data.etf_updater_cn import update_etf_prices
    total = update_etf_prices()

    # 512000.SH succeeded
    assert total == 1
    assert mock_execute.call_count == 1
    written_rows = mock_execute.call_args[0][1]
    assert written_rows[0][1] == "512000.SH"


@patch("data.etf_updater_cn.CN_SECTOR_ETFS", {"512800.SH": {"name": "银行ETF", "gics": "Financials"}})
@patch("data.etf_updater_cn.query")
@patch("data.etf_updater_cn.execute")
@patch("data.etf_updater_cn.fetch_etf_daily_hfq")
def test_update_etf_prices_full_rebase_ignores_last_date(mock_fetch, mock_execute, mock_query):
    """full_rebase=True → start from 20100101 even if last_date exists."""
    mock_query.return_value = [{"d": date(2026, 5, 12)}]
    mock_fetch.return_value = pd.DataFrame({
        "date": [date(2010, 1, 5), date(2026, 5, 13)],
        "hfq_close": [0.5, 1.8],
    })
    mock_execute.return_value = 2

    from data.etf_updater_cn import update_etf_prices
    total = update_etf_prices(full_rebase=True)

    mock_fetch.assert_called_once_with("512800.SH", start_date="20100101")
    # No last_date filter applied → both rows written
    rows = mock_execute.call_args[0][1]
    assert len(rows) == 2
```

- [ ] **Step 2: Run tests**

```bash
uv run pytest tests/test_etf_updater_cn.py -v
```

Expected: Both new tests PASS (logic already supports both via existing implementation in Task 5).

- [ ] **Step 3: Commit**

```bash
git add tests/test_etf_updater_cn.py
git commit -m "test: cover per-ETF failure isolation and full_rebase mode"
```

---

## Task 7: Hook ETF into `market_cn.update_index_price()`

**Files:**
- Modify: `data/market_cn.py`
- Create: `tests/test_market_cn_etf_hook.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_market_cn_etf_hook.py`:

```python
"""Verify update_index_price() invokes ETF updater after CSI800."""
from unittest.mock import patch, MagicMock
import pandas as pd
from datetime import date


@patch("data.etf_updater_cn.update_etf_prices")
@patch("data.market_cn.query")
@patch("data.market_cn.execute")
@patch("data.market_cn.get_client")
def test_update_index_price_calls_etf_updater(mock_get_client, mock_execute, mock_query, mock_etf_update):
    """CSI800 count + ETF count are summed."""
    mock_query.return_value = [{"d": date(2026, 5, 10)}]

    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    mock_client.call.return_value = pd.DataFrame({
        "ts_code": ["000906.SH"],
        "trade_date": ["20260513"],
        "close": [5675.0],
    })
    mock_execute.return_value = 1   # CSI800 row

    mock_etf_update.return_value = 42  # ETF rows

    from data.market_cn import update_index_price
    total = update_index_price()

    assert total == 1 + 42
    mock_etf_update.assert_called_once_with()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_market_cn_etf_hook.py -v
```

Expected: FAIL — `update_index_price()` currently returns only CSI800 count and never calls `update_etf_prices`.

- [ ] **Step 3: Refactor `data/market_cn.py` — extract CSI800 + add ETF hook**

Replace the entire existing `update_index_price()` function (currently around line 77-118) with this two-function structure:

```python
def update_index_price() -> int:
    """中证800 指数 close via tushare index_daily + 行业 ETF hfq close via fund_daily × fund_adj。"""
    csi800_count = _update_csi800()
    from data.etf_updater_cn import update_etf_prices
    etf_count = update_etf_prices()
    return csi800_count + etf_count


def _update_csi800() -> int:
    """中证800 指数 close via tushare index_daily (000906.SH)。"""
    last = query(
        "SELECT MAX(date) AS d FROM index_prices WHERE index_id=%s", ("CSI800",)
    )
    last_date = last[0]["d"] if last and last[0]["d"] else None

    client = get_client()
    ts_code = index_id_to_ts_code("CSI800")

    try:
        start_date = last_date.strftime("%Y%m%d") if last_date else None
        raw = client.call("index_daily", ts_code=ts_code, start_date=start_date)

        if raw is None or raw.empty:
            return 0

        required_cols = {"trade_date", "close"}
        if not required_cols.issubset(raw.columns):
            log.error(f"[CSI800] index_daily missing columns: {required_cols - set(raw.columns)}")
            return 0

        df = pd.DataFrame({
            "date":  pd.to_datetime(raw["trade_date"]).dt.date,
            "close": raw["close"].astype(float),
        })

        if last_date:
            df = df[df["date"] > last_date]

        if df.empty:
            return 0

        rows = [(r.date, "CSI800", to_float(r.close)) for r in df.itertuples(index=False)]
        return execute(
            "INSERT IGNORE INTO index_prices (date, index_id, close) VALUES (%s,%s,%s)",
            rows, many=True,
        )
    except Exception as e:
        log.error(f"[CSI800] index_daily failed: {e}")
        return 0
```

- [ ] **Step 4: Patch existing CSI800 tests so they mock `update_etf_prices`**

`tests/test_cn_index_price.py` currently patches `data.market_cn.query/execute/get_client` and calls `update_index_price()`. After refactor, `update_index_price()` also calls `data.etf_updater_cn.update_etf_prices` — without a mock that would try to hit real tushare and break the unit test.

Add a decorator-style fixture by editing each existing test in `tests/test_cn_index_price.py`. For every test that does `from data.market_cn import update_index_price`, add an outer decorator:

```python
@patch("data.etf_updater_cn.update_etf_prices", return_value=0)
```

Example — change:

```python
@patch("data.market_cn.query")
@patch("data.market_cn.execute")
@patch("data.market_cn.get_client")
def test_update_index_price_uses_tushare_index_daily(mock_get_client, mock_execute, mock_query):
```

To:

```python
@patch("data.etf_updater_cn.update_etf_prices", return_value=0)
@patch("data.market_cn.query")
@patch("data.market_cn.execute")
@patch("data.market_cn.get_client")
def test_update_index_price_uses_tushare_index_daily(mock_get_client, mock_execute, mock_query, mock_etf):
```

Note: outermost decorator → last positional argument. Apply this to all 6 tests in `tests/test_cn_index_price.py` that call `update_index_price()`:

- `test_update_index_price_uses_tushare_index_daily`
- `test_update_index_price_empty_response`
- `test_update_index_price_no_last_date`
- `test_update_index_price_handles_exception`
- `test_update_index_price_missing_columns`
- `test_update_index_price_none_response`

- [ ] **Step 5: Run new + existing CN index tests**

```bash
uv run pytest tests/test_market_cn_etf_hook.py tests/test_cn_index_price.py -v
```

Expected: All PASS.

- [ ] **Step 6: Commit**

```bash
git add data/market_cn.py tests/test_market_cn_etf_hook.py tests/test_cn_index_price.py
git commit -m "feat: hook ETF updater into market_cn.update_index_price"
```

---

## Task 8: CLI `rebase --etf-only` flag

**Files:**
- Modify: `main.py`
- Modify: `data/market_cn.py` (add `rebase_etf()` wrapper)
- Create: `tests/test_cli_rebase_etf.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_cli_rebase_etf.py`:

```python
"""rebase --etf-only triggers full ETF re-pull without touching stocks."""
from unittest.mock import patch


@patch("data.etf_updater_cn.update_etf_prices")
def test_rebase_etf_only_calls_update_with_full_rebase(mock_update):
    """main.py rebase --market cn --etf-only → update_etf_prices(full_rebase=True)."""
    mock_update.return_value = 100

    from main import main
    rc = main(["rebase", "--market", "cn", "--etf-only"])

    assert rc == 0
    mock_update.assert_called_once_with(full_rebase=True)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_cli_rebase_etf.py -v
```

Expected: FAIL — either argparse rejects `--etf-only` or it falls through to stock rebase.

- [ ] **Step 3: Add `--etf-only` flag to `rebase` parser**

In `main.py` find:

```python
    p_rebase = sub.add_parser("rebase", help="Full re-pull (qfq drift fix)")
    p_rebase.add_argument("--market", choices=("cn", "hk", "us"), required=True)
    p_rebase.add_argument("--code", action="append", default=None)
    p_rebase.add_argument("--years", type=int, default=None, help="历史年数（默认：US=5, CN/HK=15）")
    p_rebase.add_argument("--index", default=None,
                          help="指数成分股（仅 US 市场：SP500）")
```

Append after `--index`:

```python
    p_rebase.add_argument("--etf-only", action="store_true",
                          help="仅重灌 ETF index_prices（仅 CN 市场）")
```

- [ ] **Step 4: Dispatch `--etf-only` in `cmd_rebase`**

In `main.py` find `cmd_rebase`:

```python
def cmd_rebase(market: str, codes: list[str] | None, years: int | None, index: str | None) -> int:
```

Replace with (add `etf_only` param + early branch):

```python
def cmd_rebase(market: str, codes: list[str] | None, years: int | None, index: str | None, etf_only: bool = False) -> int:
    if etf_only:
        if market != "cn":
            print(f"--etf-only currently only supports --market cn", file=sys.stderr)
            return 1
        from data.etf_updater_cn import update_etf_prices
        n = update_etf_prices(full_rebase=True)
        print(f"[cn] ETF rebase wrote {n} rows to index_prices")
        return 0

    import inspect
    mod = _import_market(market)
    if not hasattr(mod, "rebase"):
        print(f"[{market}] rebase not implemented", file=sys.stderr)
        return 1

    sig_list = inspect.signature(mod.list_active_tickers)
    if 'index' in sig_list.parameters:
        targets = codes or mod.list_active_tickers(index=index)
    else:
        targets = codes or mod.list_active_tickers()

    years_msg = f" ({years} 年)" if years else ""
    index_msg = f" [{index}]" if index else ""
    print(f"[{market}] rebase {len(targets)} tickers{index_msg}{years_msg} (full history)")

    sig_rebase = inspect.signature(mod.rebase)
    if 'index' in sig_rebase.parameters:
        mod.rebase(targets, years=years, index=index)
    else:
        mod.rebase(targets, years=years)

    return 0
```

Also update the dispatch in `main()`:

```python
    if args.cmd == "rebase":
        return cmd_rebase(args.market, args.code, args.years, args.index)
```

Replace with:

```python
    if args.cmd == "rebase":
        return cmd_rebase(args.market, args.code, args.years, args.index, args.etf_only)
```

- [ ] **Step 5: Run the new test + full test suite**

```bash
uv run pytest tests/test_cli_rebase_etf.py -v
uv run pytest tests/ -v
```

Expected: All PASS.

- [ ] **Step 6: Commit**

```bash
git add main.py tests/test_cli_rebase_etf.py
git commit -m "feat: add 'rebase --market cn --etf-only' for full ETF re-pull"
```

---

## Task 9: README documentation

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Locate ETF docs section**

```bash
grep -n "QQQ\|XLK\|行业 ETF\|index_prices" README.md
```

Find the existing "US sector ETF" / `index_prices` section.

- [ ] **Step 2: Append CN ETF section**

After the existing US ETF query example block, insert:

````markdown
### CN 行业 ETF 数据

A股行业 ETF 后复权日线（hfq close）via tushare `fund_daily × fund_adj`，存 `index_prices` 表，`index_id` 为 ts_code（如 `512800.SH`）。

清单：`config.CN_SECTOR_ETFS`，按 GICS 11 类对齐 US XL* + A 股主题（光伏/新能源车/芯片），共 ~17 只。

跑法：

```bash
uv run main.py daily --market cn        # 自动包含 ETF
uv run main.py rebase --market cn --etf-only   # 仅 ETF 全量重灌（季度执行修正分红 drift）
```

查询示例：

```sql
-- CN vs US 同行业横向对比（银行 vs 美国金融）
SELECT date, index_id, close
FROM index_prices
WHERE index_id IN ('512800.SH', 'XLF')
  AND date >= '2026-01-01'
ORDER BY date, index_id;

-- 查 CN HealthCare 板块两只 ETF
SELECT date, index_id, close
FROM index_prices
WHERE index_id IN ('512170.SH', '512010.SH')
ORDER BY date;
```

ETF 列表：

| ts_code | 名称 | GICS / 主题 |
|---|---|---|
| 515220.SH | 煤炭ETF | Energy |
| 512400.SH | 有色金属ETF | Materials |
| 512660.SH | 军工ETF | Industrials |
| 159996.SZ | 家电ETF | ConsumerDiscretionary |
| 512690.SH | 酒ETF | ConsumerStaples |
| 512170.SH | 医疗ETF | HealthCare |
| 512010.SH | 医药ETF | HealthCare |
| 512800.SH | 银行ETF | Financials |
| 512000.SH | 券商ETF | Financials |
| 512720.SH | 计算机ETF | InformationTechnology |
| 512480.SH | 半导体ETF | InformationTechnology |
| 515050.SH | 5G通信ETF | CommunicationServices |
| 159611.SZ | 电力ETF | Utilities |
| 512200.SH | 房地产ETF | RealEstate |
| 515790.SH | 光伏ETF | Theme.Solar |
| 515030.SH | 新能源车ETF | Theme.NEV |
| 159995.SZ | 芯片ETF | Theme.Chip |
````

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: add CN sector ETF section to README"
```

---

## Task 10: End-to-end smoke test on real DB

**Files:** None (read-only verification)

- [ ] **Step 1: Run daily ingest**

```bash
uv run main.py daily --market cn 2>&1 | tee /tmp/cn-etf-daily.log
```

Expected: Log lines `[<ts_code>] <name> 写入 N 行` for each of the 17 ETFs.

- [ ] **Step 2: Verify rows in DB**

```bash
uv run python -c "
from db import query
rows = query('''
  SELECT index_id, COUNT(*) AS n, MIN(date) AS first, MAX(date) AS last
  FROM index_prices
  WHERE index_id LIKE '%.SH' OR index_id LIKE '%.SZ'
  GROUP BY index_id
  ORDER BY index_id
''')
for r in rows:
    print(r)
"
```

Expected: 17 rows, each with `n > 1000` (15 years of trading days ≈ 3650), `first` near 2010/2013/2015 (ETF inception), `last` = today (or last trading day).

- [ ] **Step 3: Cross-market join sanity check**

```bash
uv run python -c "
from db import query
rows = query('''
  SELECT date, index_id, close
  FROM index_prices
  WHERE index_id IN ('512800.SH', 'XLF')
    AND date >= '2026-01-01'
  ORDER BY date DESC, index_id
  LIMIT 10
''')
for r in rows:
    print(r)
"
```

Expected: Both `512800.SH` and `XLF` rows interleaved by date.

- [ ] **Step 4: Run full test suite as final gate**

```bash
uv run pytest tests/ -v
```

Expected: All PASS.

- [ ] **Step 5: No new commit needed** (smoke test only, no file changes)

---

## Verification Checklist

- [ ] `uv run pytest tests/test_etf_updater_cn.py -v` — all 6 tests PASS
- [ ] `uv run pytest tests/test_market_cn_etf_hook.py -v` — PASS
- [ ] `uv run pytest tests/test_cli_rebase_etf.py -v` — PASS
- [ ] `uv run pytest tests/test_config.py::test_cn_sector_etfs_covers_gics_11 -v` — PASS
- [ ] `uv run python scripts/verify_cn_etfs.py` — `OK: 全部 17 只 ETF 存在`
- [ ] `uv run main.py daily --market cn` — 17 ETF 写入日志可见
- [ ] DB 查询确认 17 个 ts_code 在 `index_prices` 表有数据
- [ ] CN-vs-US 横向 SQL join 工作正常
- [ ] `uv run pytest tests/ -v` — 全套测试无回归
