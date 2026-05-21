# CN Weekly Price Ingest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `uv run main.py weekly --market cn` that pulls tushare weekly (freq=W, qfq) prices into `prices_weekly`, with sync_log tracking, leaving daily ingest untouched.

**Architecture:** New `data/stock_updater_cn_weekly.py` mirrors `stock_updater_cn_tushare.py` with `freq="W"` and `prices_weekly` table. `market_cn.py` gets one new `weekly()` function appended. `main.py` widens `--market` choices to `us|cn` and simplifies `cmd_weekly` to call `mod.weekly(codes)` generically.

**Tech Stack:** tushare pro_bar (freq=W), pymysql, pytest + unittest.mock

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `data/stock_updater_cn_weekly.py` | **Create** | CN weekly fetch + write `prices_weekly` + sync_log |
| `data/market_cn.py` | **Append** | `weekly()` thin adapter |
| `main.py` | **Modify** | Widen `--market` choices; simplify `cmd_weekly` |
| `tests/test_stock_updater_cn_weekly.py` | **Create** | Unit tests |

`data/stock_updater_cn_tushare.py` / `data/pipeline.py` — **zero changes**.

---

## Task 1: Write failing tests for `stock_updater_cn_weekly`

**Files:**
- Create: `tests/test_stock_updater_cn_weekly.py`

- [ ] **Step 1: Create the test file**

```python
# tests/test_stock_updater_cn_weekly.py
import pytest
from datetime import date
from unittest.mock import patch, MagicMock
import pandas as pd


# ── _normalize_pro_bar ────────────────────────────────────────────────────────

def test_normalize_pro_bar_happy_path():
    from data.stock_updater_cn_weekly import _normalize_pro_bar
    df = pd.DataFrame({
        "trade_date": ["20260511", "20260518"],
        "open":  [100.0, 102.0],
        "high":  [105.0, 106.0],
        "low":   [99.0,  101.0],
        "close": [103.0, 104.0],
        "vol":   [1_000_000, 1_200_000],
    })
    result = _normalize_pro_bar(df)
    assert list(result.columns) == ["date", "open", "high", "low", "close", "volume"]
    assert len(result) == 2
    assert result["date"].iloc[0] == date(2026, 5, 11)
    assert result["close"].iloc[1] == 104.0


def test_normalize_pro_bar_empty():
    from data.stock_updater_cn_weekly import _normalize_pro_bar
    result = _normalize_pro_bar(pd.DataFrame())
    assert result.empty


def test_normalize_pro_bar_sorted_ascending():
    """Rows returned in ascending date order regardless of tushare order."""
    from data.stock_updater_cn_weekly import _normalize_pro_bar
    df = pd.DataFrame({
        "trade_date": ["20260518", "20260511"],  # reversed
        "open":  [102.0, 100.0],
        "high":  [106.0, 105.0],
        "low":   [101.0, 99.0],
        "close": [104.0, 103.0],
        "vol":   [1_200_000, 1_000_000],
    })
    result = _normalize_pro_bar(df)
    assert result["date"].iloc[0] == date(2026, 5, 11)
    assert result["date"].iloc[1] == date(2026, 5, 18)


# ── _save_weekly_prices_batch ─────────────────────────────────────────────────

def test_save_weekly_prices_batch_uses_prices_weekly_table():
    from data.stock_updater_cn_weekly import _save_weekly_prices_batch
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value.__enter__ = lambda s: mock_cur
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

    rows = [("600519.SH", date(2026, 5, 15), 100.0, 105.0, 99.0, 103.0, 1_000_000)]
    count = _save_weekly_prices_batch(mock_conn, rows)

    assert count == 1
    assert mock_cur.executemany.called
    sql = mock_cur.executemany.call_args[0][0]
    assert "prices_weekly" in sql
    assert "ON DUPLICATE KEY UPDATE" in sql


# ── update_weekly_batch ───────────────────────────────────────────────────────

def test_update_weekly_batch_empty():
    from data.stock_updater_cn_weekly import update_weekly_batch
    assert update_weekly_batch([]) == {}


def test_update_weekly_batch_all_already_synced():
    """All tickers already at last_trading: skips without fetching."""
    from data.stock_updater_cn_weekly import update_weekly_batch
    with patch("data.stock_updater_cn_weekly._last_cn_trading_date",
               return_value=date(2026, 5, 16)), \
         patch("data.stock_updater_cn_weekly.get_conn") as mock_conn_fn, \
         patch("data.stock_updater_cn_weekly.get_last_sync",
               return_value=date(2026, 5, 16)):
        mock_conn = MagicMock()
        mock_conn_fn.return_value = mock_conn
        result = update_weekly_batch(["600519.SH", "000001.SZ"])
    assert result == {}


def test_update_weekly_batch_new_tickers_trigger_full_backfill():
    """New tickers (no sync_log) trigger full history fetch."""
    from data.stock_updater_cn_weekly import update_weekly_batch
    from config import TUSHARE_BACKFILL_START

    weekly_df = pd.DataFrame({
        "trade_date": ["20260516"],
        "open":  [100.0],
        "high":  [105.0],
        "low":   [99.0],
        "close": [103.0],
        "vol":   [1_000_000],
    })

    with patch("data.stock_updater_cn_weekly._last_cn_trading_date",
               return_value=date(2026, 5, 16)), \
         patch("data.stock_updater_cn_weekly.get_conn") as mock_conn_fn, \
         patch("data.stock_updater_cn_weekly.get_last_sync", return_value=None), \
         patch("data.stock_updater_cn_weekly._fetch_one", return_value=pd.DataFrame({
             "date": [date(2026, 5, 16)],
             "open": [100.0], "high": [105.0], "low": [99.0],
             "close": [103.0], "volume": [1_000_000],
         })) as mock_fetch, \
         patch("data.stock_updater_cn_weekly._flush_batch"):
        mock_conn = MagicMock()
        mock_conn_fn.return_value = mock_conn
        result = update_weekly_batch(["600519.SH"])

    assert mock_fetch.called
    start_arg = mock_fetch.call_args[0][1]
    assert start_arg == TUSHARE_BACKFILL_START


def test_sync_data_type_is_price_weekly():
    """SYNC_DATA_TYPE constant must be 'price_weekly'."""
    from data.stock_updater_cn_weekly import SYNC_DATA_TYPE
    assert SYNC_DATA_TYPE == "price_weekly"
```

- [ ] **Step 2: Run tests — confirm ImportError**

```bash
uv run pytest tests/test_stock_updater_cn_weekly.py -v 2>&1 | head -20
```

Expected: all FAIL with `ModuleNotFoundError: No module named 'data.stock_updater_cn_weekly'`

- [ ] **Step 3: Commit**

```bash
git add tests/test_stock_updater_cn_weekly.py
git commit -m "test: add failing tests for stock_updater_cn_weekly"
```

---

## Task 2: Implement `data/stock_updater_cn_weekly.py`

**Files:**
- Create: `data/stock_updater_cn_weekly.py`

- [ ] **Step 1: Create the module**

```python
# data/stock_updater_cn_weekly.py
"""A-share weekly-K updater via Tushare (pre-adjusted, qfq).

与 stock_updater_cn_tushare.py 完全对称，差异：
- pro_bar(freq="W") 拉取周线
- 写入 prices_weekly 表
- sync_log data_type = "price_weekly"
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Dict, List, Tuple, Optional

import pandas as pd

from config import TUSHARE_BACKFILL_START
from db import get_conn, get_last_sync
from data.base import to_float, to_int
from data.stock_updater_cn_tushare import _last_cn_trading_date
from ts_ingest.client import get_client

log = logging.getLogger(__name__)

SYNC_DATA_TYPE = "price_weekly"
BATCH_COMMIT_SIZE = 50


def _normalize_pro_bar(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    out = pd.DataFrame({
        "date":   pd.to_datetime(df["trade_date"], format="%Y%m%d").dt.date,
        "open":   df["open"].apply(to_float),
        "high":   df["high"].apply(to_float),
        "low":    df["low"].apply(to_float),
        "close":  df["close"].apply(to_float),
        "volume": df["vol"].apply(to_int),
    })
    return out.sort_values("date").reset_index(drop=True)


def _fetch_one(ticker: str, start: str, end: str) -> pd.DataFrame:
    """tushare pro_bar 单ticker周线拉取。start/end格式YYYYMMDD。"""
    client = get_client()
    df_raw = client.pro_bar(ts_code=ticker, adj="qfq", start_date=start, end_date=end, freq="W")
    return _normalize_pro_bar(df_raw)


def _save_weekly_prices_batch(conn, rows: List[Tuple]) -> int:
    """批量写入prices_weekly表，不commit（由调用者控制）。"""
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


def _flush_batch(conn, prices_buf: List[Tuple], sync_buf: List[Tuple]):
    """批量commit prices_weekly + sync_log。"""
    if prices_buf:
        _save_weekly_prices_batch(conn, prices_buf)
    if sync_buf:
        sql = """
            INSERT INTO sync_log
              (ticker, data_type, last_date, rows_added, status, message)
            VALUES (%s,%s,%s,%s,%s,%s)
            ON DUPLICATE KEY UPDATE
              last_date  = IF(VALUES(status)='ok', VALUES(last_date), last_date),
              rows_added = VALUES(rows_added),
              last_run   = CURRENT_TIMESTAMP,
              status     = VALUES(status),
              message    = VALUES(message)
        """
        with conn.cursor() as cur:
            cur.executemany(sql, sync_buf)
    conn.commit()


def _process_tickers_batched(
    conn, tickers: List[str], last_trading: date,
    full_rebase: bool, result: Dict[str, str],
    progress_label: str = "补缺",
    years: Optional[int] = None,
) -> Tuple[List[Tuple], List[Tuple]]:
    """批量处理ticker，返回未flush的buffer。"""
    prices_buf: List[Tuple] = []
    sync_buf: List[Tuple] = []

    for i, t in enumerate(tickers, 1):
        try:
            if full_rebase:
                if years:
                    start_date = last_trading - timedelta(days=365 * years)
                    start = start_date.strftime("%Y%m%d")
                else:
                    start = TUSHARE_BACKFILL_START
            else:
                last = get_last_sync(conn, t, SYNC_DATA_TYPE)
                if last:
                    start = (last + timedelta(days=1)).strftime("%Y%m%d")
                else:
                    start = TUSHARE_BACKFILL_START
            end = last_trading.strftime("%Y%m%d")

            df = _fetch_one(t, start, end)
            if df.empty:
                if end == date.today().strftime("%Y%m%d"):
                    sync_buf.append((t, SYNC_DATA_TYPE, date.today(), 0, "error", "tushare: no data"))
                    result[t] = "no_data"
                else:
                    result[t] = "skip"
                if len(sync_buf) >= BATCH_COMMIT_SIZE:
                    _flush_batch(conn, prices_buf, sync_buf)
                    prices_buf.clear()
                    sync_buf.clear()
                continue

            for _, r in df.iterrows():
                prices_buf.append((
                    t, r["date"],
                    to_float(r["open"]), to_float(r["high"]),
                    to_float(r["low"]), to_float(r["close"]),
                    to_int(r["volume"]),
                ))
            new_last = df["date"].max()
            rows_count = len(df)
            sync_buf.append((t, SYNC_DATA_TYPE, new_last, rows_count, "ok", ""))
            result[t] = "ok"

            if len(sync_buf) >= BATCH_COMMIT_SIZE:
                _flush_batch(conn, prices_buf, sync_buf)
                log.info(f"[cn weekly] {progress_label}进度 {i}/{len(tickers)} (batch flush)")
                prices_buf.clear()
                sync_buf.clear()

        except Exception as e:
            _flush_batch(conn, prices_buf, sync_buf)
            prices_buf.clear()
            sync_buf.clear()
            sync_buf.append((t, SYNC_DATA_TYPE, date.today(), 0, "error", str(e)[:500]))
            _flush_batch(conn, [], sync_buf)
            sync_buf.clear()
            log.error(f"[{t}] {progress_label}失败: {e}")
            result[t] = f"error: {e}"

        if i % 100 == 0 and len(sync_buf) < BATCH_COMMIT_SIZE:
            log.info(f"[cn weekly] {progress_label}进度 {i}/{len(tickers)}")

    return prices_buf, sync_buf


def update_weekly_batch(
    tickers: List[str],
    full_rebase: bool = False,
    years: Optional[int] = None,
) -> Dict[str, str]:
    """批量增量拉取A股周线，写入 prices_weekly 表。

    Args:
      tickers: canonical A-share tickers (e.g., 600519.SH)
      full_rebase: if True, ignore sync_log and pull from TUSHARE_BACKFILL_START
      years: 指定历史年数（None 时使用 TUSHARE_BACKFILL_START）

    Returns: {ticker: status}
    """
    if not tickers:
        return {}

    last_trading = _last_cn_trading_date()
    result: Dict[str, str] = {}

    conn = get_conn()
    try:
        new_tickers = []
        pending_tickers = []

        for t in tickers:
            if full_rebase:
                pending_tickers.append(t)
                continue
            last = get_last_sync(conn, t, SYNC_DATA_TYPE)
            if last is None:
                new_tickers.append(t)
            elif last < last_trading:
                pending_tickers.append(t)

        log.info(f"[cn weekly] 总数={len(tickers)}, new={len(new_tickers)}, pending={len(pending_tickers)}")

        if new_tickers:
            log.info(f"[cn weekly] {len(new_tickers)} 新ticker需回填历史")
            buf_p, buf_s = _process_tickers_batched(
                conn, new_tickers, last_trading,
                full_rebase=True, result=result,
                progress_label="回填", years=years,
            )
            _flush_batch(conn, buf_p, buf_s)

        if pending_tickers:
            log.info(f"[cn weekly] {len(pending_tickers)} ticker需增量补缺")
            buf_p, buf_s = _process_tickers_batched(
                conn, pending_tickers, last_trading,
                full_rebase=full_rebase, result=result,
                progress_label="补缺" if not full_rebase else "回填",
                years=years if full_rebase else None,
            )
            _flush_batch(conn, buf_p, buf_s)

        if not new_tickers and not pending_tickers:
            log.info(f"[cn weekly] 所有ticker已同步到 {last_trading}")

        return result
    finally:
        conn.close()
```

- [ ] **Step 2: Run tests — all must pass**

```bash
uv run pytest tests/test_stock_updater_cn_weekly.py -v
```

Expected: 7 tests PASS.

- [ ] **Step 3: Commit**

```bash
git add data/stock_updater_cn_weekly.py
git commit -m "feat: add stock_updater_cn_weekly — weekly price ingest for CN market"
```

---

## Task 3: Add `weekly()` to `market_cn.py` + fix `main.py`

**Files:**
- Modify: `data/market_cn.py` (append only)
- Modify: `main.py` (widen choices + simplify cmd_weekly)

- [ ] **Step 1: Append `weekly()` to `data/market_cn.py`**

After the last function (`rebase`), append:

```python


def weekly(tickers: list[str] | None = None) -> dict[str, str]:
    """Pull weekly prices for CN universe into prices_weekly."""
    from data import stock_updater_cn_weekly
    targets = tickers or list_active_tickers()
    return stock_updater_cn_weekly.update_weekly_batch(targets)
```

- [ ] **Step 2: Widen `--market` choices in `main.py`**

In `_build_parser()`, find:
```python
    p_weekly.add_argument("--market", choices=("us",), default="us")
```
Replace with:
```python
    p_weekly.add_argument("--market", choices=("us", "cn"), default="us")
```

- [ ] **Step 3: Simplify `cmd_weekly` in `main.py`**

Find the entire `cmd_weekly` function:
```python
def cmd_weekly(market: str, codes: list[str] | None) -> int:
    mod = _import_market(market)
    if codes:
        print(f"[{market}] weekly --code {codes}: running single-ticker mode")
        from data import stock_updater_us_weekly
        result = stock_updater_us_weekly.update_weekly_batch(codes)
    else:
        result = mod.weekly()
    ok = sum(1 for v in result.values() if v == "ok")
    print(f"[{market}] weekly done: {ok}/{len(result)} ok")
    return 0
```
Replace it with:
```python
def cmd_weekly(market: str, codes: list[str] | None) -> int:
    mod = _import_market(market)
    result = mod.weekly(codes)
    ok = sum(1 for v in result.values() if v == "ok")
    print(f"[{market}] weekly done: {ok}/{len(result)} ok")
    return 0
```

- [ ] **Step 4: Run full test suite**

```bash
uv run pytest tests/ --ignore=tests/test_db_smoke.py -x 2>&1 | tail -20
```

Expected: all tests PASS.

- [ ] **Step 5: Smoke-test CLI help**

```bash
uv run python main.py weekly --help
```

Expected output includes: `--market {us,cn}`

- [ ] **Step 6: Commit**

```bash
git add data/market_cn.py main.py
git commit -m "feat: add CN weekly support — extend weekly subcommand to --market us|cn"
```

---

## Task 4: Final verification

- [ ] **Step 1: Run full test suite**

```bash
uv run pytest tests/ --ignore=tests/test_db_smoke.py -v 2>&1 | tail -20
```

Expected: all tests PASS, no regressions.

- [ ] **Step 2: Verify CLI routing**

```bash
uv run python main.py weekly --market cn --help
uv run python main.py weekly --market us --help
```

Both must show valid help without error.

- [ ] **Step 3: Done**

CN weekly ready. Cron schedule (example — Saturdays after A-share Friday close):
```bash
uv run main.py weekly --market us
uv run main.py weekly --market cn
```
Or unified if run daily:
```bash
uv run main.py weekly --market us && uv run main.py weekly --market cn
```
