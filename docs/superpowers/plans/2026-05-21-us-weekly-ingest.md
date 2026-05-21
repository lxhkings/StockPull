# US Weekly Price Ingest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `uv run main.py weekly --market us` command that pulls yfinance weekly (1wk) prices into `prices_weekly`, with sync_log tracking, leaving daily ingest untouched.

**Architecture:** New standalone module `data/stock_updater_us_weekly.py` mirrors daily logic with `interval="1wk"` and `data_type="price_weekly"`. `market_us.py` gets one new function appended. `main.py` gets a new subcommand. No existing code modified.

**Tech Stack:** yfinance, pymysql, pytest + unittest.mock

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `data/stock_updater_us_weekly.py` | **Create** | Weekly download, AAPL precheck, write `prices_weekly`, sync_log |
| `data/market_us.py` | **Append** | `weekly()` function — thin adapter |
| `main.py` | **Append** | `weekly` subcommand + `cmd_weekly()` routing |
| `tests/test_stock_updater_us_weekly.py` | **Create** | Unit tests for all new logic |

---

## Task 1: Write failing tests for `stock_updater_us_weekly`

**Files:**
- Create: `tests/test_stock_updater_us_weekly.py`

- [ ] **Step 1: Create the test file**

```python
# tests/test_stock_updater_us_weekly.py
import pytest
from datetime import date
from unittest.mock import patch, MagicMock, call
import pandas as pd


# ── _last_us_weekly_date ──────────────────────────────────────────────────────

def test_last_us_weekly_date_monday_morning_returns_prev_monday():
    """Monday before 5am: previous week's Monday."""
    from datetime import datetime
    with patch("data.stock_updater_us_weekly.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2026, 5, 18, 3, 0)  # Monday 03:00
        from data.stock_updater_us_weekly import _last_us_weekly_date
        result = _last_us_weekly_date()
    assert result == date(2026, 5, 11)  # Monday of previous week
    assert result.weekday() == 0


def test_last_us_weekly_date_friday_returns_prev_monday():
    """Friday (any time): previous week's Monday."""
    from datetime import datetime
    with patch("data.stock_updater_us_weekly.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2026, 5, 22, 20, 0)  # Friday 20:00
        from data.stock_updater_us_weekly import _last_us_weekly_date
        result = _last_us_weekly_date()
    assert result == date(2026, 5, 11)
    assert result.weekday() == 0


def test_last_us_weekly_date_saturday_after_5am_returns_this_monday():
    """Saturday after 5am Beijing: week Mon-Fri just closed, return this week's Monday."""
    from datetime import datetime
    with patch("data.stock_updater_us_weekly.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2026, 5, 23, 6, 0)  # Saturday 06:00
        from data.stock_updater_us_weekly import _last_us_weekly_date
        result = _last_us_weekly_date()
    assert result == date(2026, 5, 18)  # Monday of week that just closed
    assert result.weekday() == 0


def test_last_us_weekly_date_saturday_before_5am_returns_prev_monday():
    """Saturday before 5am Beijing: Friday US not yet closed."""
    from datetime import datetime
    with patch("data.stock_updater_us_weekly.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2026, 5, 23, 4, 0)  # Saturday 04:00
        from data.stock_updater_us_weekly import _last_us_weekly_date
        result = _last_us_weekly_date()
    assert result == date(2026, 5, 11)
    assert result.weekday() == 0


def test_last_us_weekly_date_sunday_returns_this_monday():
    """Sunday: last week's Mon-Fri is complete."""
    from datetime import datetime
    with patch("data.stock_updater_us_weekly.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2026, 5, 24, 12, 0)  # Sunday noon
        from data.stock_updater_us_weekly import _last_us_weekly_date
        result = _last_us_weekly_date()
    assert result == date(2026, 5, 18)
    assert result.weekday() == 0


# ── update_weekly_batch precheck ──────────────────────────────────────────────

def test_update_weekly_batch_empty_returns_empty():
    from data.stock_updater_us_weekly import update_weekly_batch
    assert update_weekly_batch([]) == {}


def test_update_weekly_batch_rate_limit_skips_all():
    from data.stock_updater_us_weekly import update_weekly_batch
    with patch("data.stock_updater_us_weekly._last_us_weekly_date", return_value=date(2026, 5, 11)), \
         patch("data.stock_updater_us_weekly._test_aapl_weekly", return_value=(None, "rate_limit")):
        result = update_weekly_batch(["AAPL", "MSFT"])
    assert result == {"AAPL": "error: rate_limit", "MSFT": "error: rate_limit"}


def test_update_weekly_batch_no_data_skips_all():
    from data.stock_updater_us_weekly import update_weekly_batch
    with patch("data.stock_updater_us_weekly._last_us_weekly_date", return_value=date(2026, 5, 11)), \
         patch("data.stock_updater_us_weekly._test_aapl_weekly", return_value=(None, "no_data")):
        result = update_weekly_batch(["AAPL"])
    assert result == {"AAPL": "error: no_data"}


def test_update_weekly_batch_test_error_skips_all():
    from data.stock_updater_us_weekly import update_weekly_batch
    with patch("data.stock_updater_us_weekly._last_us_weekly_date", return_value=date(2026, 5, 11)), \
         patch("data.stock_updater_us_weekly._test_aapl_weekly", return_value=(None, "error")):
        result = update_weekly_batch(["AAPL"])
    assert result == {"AAPL": "error: test_failed"}


# ── _normalize_weekly_frame ───────────────────────────────────────────────────

def test_normalize_weekly_frame_empty_returns_empty():
    from data.stock_updater_us_weekly import _normalize_weekly_frame
    result = _normalize_weekly_frame("AAPL", pd.DataFrame())
    assert result.empty
    assert list(result.columns) == ["ticker", "date", "open", "high", "low", "close", "volume"]


def test_normalize_weekly_frame_happy_path():
    from data.stock_updater_us_weekly import _normalize_weekly_frame
    sub = pd.DataFrame({
        "Date": pd.to_datetime(["2026-05-04", "2026-05-11"]),
        "Open": [180.0, 185.0],
        "High": [182.0, 187.0],
        "Low": [178.0, 183.0],
        "Close": [181.0, 186.0],
        "Volume": [1_000_000, 1_200_000],
    })
    result = _normalize_weekly_frame("AAPL", sub)
    assert list(result.columns) == ["ticker", "date", "open", "high", "low", "close", "volume"]
    assert len(result) == 2
    assert result["ticker"].iloc[0] == "AAPL"
    assert result["date"].iloc[0] == date(2026, 5, 4)
    assert result["close"].iloc[1] == 186.0


def test_normalize_weekly_frame_drops_null_close():
    from data.stock_updater_us_weekly import _normalize_weekly_frame
    import numpy as np
    sub = pd.DataFrame({
        "Date": pd.to_datetime(["2026-05-04", "2026-05-11"]),
        "Open": [180.0, 185.0],
        "High": [182.0, 187.0],
        "Low": [178.0, 183.0],
        "Close": [None, 186.0],
        "Volume": [1_000_000, 1_200_000],
    })
    result = _normalize_weekly_frame("AAPL", sub)
    assert len(result) == 1
    assert result["date"].iloc[0] == date(2026, 5, 11)


# ── _save_weekly_prices ───────────────────────────────────────────────────────

def test_save_weekly_prices_uses_prices_weekly_table():
    from data.stock_updater_us_weekly import _save_weekly_prices
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value.__enter__ = lambda s: mock_cur
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

    df = pd.DataFrame({
        "ticker": ["AAPL", "AAPL"],
        "date": [date(2026, 5, 4), date(2026, 5, 11)],
        "open": [180.0, 185.0],
        "high": [182.0, 187.0],
        "low": [178.0, 183.0],
        "close": [181.0, 186.0],
        "volume": [1_000_000, 1_200_000],
    })
    count = _save_weekly_prices(mock_conn, "AAPL", df)
    assert count == 2
    assert mock_cur.executemany.called
    sql = mock_cur.executemany.call_args[0][0]
    assert "prices_weekly" in sql
    assert "INSERT IGNORE" in sql
```

- [ ] **Step 2: Run tests to confirm they all fail (module not found)**

```bash
cd /Users/xiaohongliang/projects/StockPull
uv run pytest tests/test_stock_updater_us_weekly.py -v 2>&1 | head -30
```

Expected: `ModuleNotFoundError: No module named 'data.stock_updater_us_weekly'`

- [ ] **Step 3: Commit failing tests**

```bash
git add tests/test_stock_updater_us_weekly.py
git commit -m "test: add failing tests for stock_updater_us_weekly"
```

---

## Task 2: Implement `data/stock_updater_us_weekly.py`

**Files:**
- Create: `data/stock_updater_us_weekly.py`

- [ ] **Step 1: Create the module**

```python
# data/stock_updater_us_weekly.py
"""
stock_updater_us_weekly.py — 美股周线行情更新

数据源：yfinance (interval="1wk")
写入：prices_weekly 表
sync_log data_type: "price_weekly"

逻辑完全镜像 stock_updater_us.py，差异仅在 interval、表名、data_type。
"""

import time
import signal
import random
import logging
from datetime import datetime, timedelta, date
from typing import Optional, List, Dict

import pandas as pd
import yfinance as yf

from config import (
    START_DATE_US,
    YF_BATCH_SIZE, YF_RETRY_COUNT, YF_TIMEOUT,
    YF_LOOKBACK_DAYS, YF_THREADS,
    YF_BATCH_DELAY_BASE, YF_BATCH_DELAY_JITTER,
)
from db import get_conn, get_last_sync, set_sync_ok, set_sync_error
from data.base import to_float, to_int

log = logging.getLogger(__name__)


def _last_us_weekly_date() -> date:
    """Return Monday of the most recently completed US trading week.

    A week is complete when Friday US close passes (Beijing time: Saturday ~5am).
    yfinance uses Monday as the canonical date for each week.
    """
    now = datetime.now()
    weekday = now.weekday()  # 0=Mon, 5=Sat, 6=Sun
    hour = now.hour
    today = now.date()
    this_monday = today - timedelta(days=weekday)

    # Saturday after 5am Beijing, or Sunday: this week (Mon-Fri) just closed
    if (weekday == 5 and hour >= 5) or weekday == 6:
        return this_monday  # Monday of the week that ended this Friday
    # Mon-Fri, or Saturday before 5am: current week not complete
    return this_monday - timedelta(days=7)  # Monday of the previous week


def _test_aapl_weekly(target_monday: date) -> tuple[Optional[pd.DataFrame], str]:
    """Test if yfinance has weekly data for the week starting target_monday."""
    start = target_monday - timedelta(days=14)
    end = target_monday + timedelta(days=7)
    try:
        signal.signal(signal.SIGINT, signal.SIG_DFL)
        df = yf.download(
            tickers="AAPL",
            start=start.strftime("%Y-%m-%d"),
            end=end.strftime("%Y-%m-%d"),
            interval="1wk",
            progress=False,
            timeout=30,
        )
        if df is None or df.empty:
            return None, "no_data"
        df = df.reset_index()
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df.columns = [str(c).lower() for c in df.columns]
        if "date" not in df.columns and "datetime" in df.columns:
            df = df.rename(columns={"datetime": "date"})
        df["date"] = pd.to_datetime(df["date"]).dt.date
        if target_monday in df["date"].values:
            return df, "ok"
        return None, "no_data"
    except Exception as e:
        err_msg = str(e)
        if "RateLimit" in err_msg or "Too Many Requests" in err_msg:
            log.warning(f"[AAPL weekly] yfinance 被限速: {e}")
            return None, "rate_limit"
        log.warning(f"[AAPL weekly] 测试请求失败: {e}")
        return None, "error"


def update_weekly_batch(tickers: List[str], full_rebase: bool = False) -> Dict[str, str]:
    """批量增量拉取周线，写入 prices_weekly 表。

    Args:
        tickers: DB 格式 ticker 列表
        full_rebase: True 时强制从 START_DATE_US 全量拉取

    Returns:
        {ticker: "ok" | "no_data" | "error: <msg>"}
    """
    if not tickers:
        return {}

    target_monday = _last_us_weekly_date()
    _, status = _test_aapl_weekly(target_monday)

    if status == "rate_limit":
        log.warning("[AAPL weekly] yfinance 被限速，跳过本次周线更新")
        return {t: "error: rate_limit" for t in tickers}
    elif status == "no_data":
        log.warning(f"[AAPL weekly] yfinance 暂无 {target_monday} 周线数据，跳过")
        return {t: "error: no_data" for t in tickers}
    elif status == "error":
        log.warning("[AAPL weekly] 测试请求失败，跳过本次周线更新")
        return {t: "error: test_failed" for t in tickers}

    log.info(f"[AAPL weekly] yfinance 已有 {target_monday} 周线数据，开始批量下载")

    result = {}
    conn = get_conn()
    try:
        if full_rebase:
            log.info(f"[weekly batch] rebase: {len(tickers)} ticker 全量历史")
            for i in range(0, len(tickers), YF_BATCH_SIZE):
                batch = tickers[i:i + YF_BATCH_SIZE]
                _download_and_save_weekly(conn, batch, None, result)
                if i + YF_BATCH_SIZE < len(tickers):
                    delay = YF_BATCH_DELAY_BASE + random.uniform(
                        -YF_BATCH_DELAY_JITTER, YF_BATCH_DELAY_JITTER
                    )
                    time.sleep(delay)
        else:
            new_tickers = []
            pending_tickers = []
            pending_start = None
            lookback_floor = target_monday - timedelta(days=YF_LOOKBACK_DAYS)

            for t in tickers:
                last = get_last_sync(conn, t, "price_weekly")
                if last is None:
                    new_tickers.append(t)
                elif last < target_monday:
                    start_dt = max(last + timedelta(days=1), lookback_floor)
                    pending_tickers.append(t)
                    if pending_start is None or start_dt < pending_start:
                        pending_start = start_dt
                # last >= target_monday: already up-to-date, skip

            if new_tickers:
                log.info(f"[weekly batch] {len(new_tickers)} 新 ticker 需回填全量历史")
                for i in range(0, len(new_tickers), YF_BATCH_SIZE):
                    batch_new = new_tickers[i:i + YF_BATCH_SIZE]
                    _download_and_save_weekly(conn, batch_new, None, result)
                    if i + YF_BATCH_SIZE < len(new_tickers):
                        delay = YF_BATCH_DELAY_BASE + random.uniform(
                            -YF_BATCH_DELAY_JITTER, YF_BATCH_DELAY_JITTER
                        )
                        time.sleep(delay)

            if pending_tickers:
                log.info(
                    f"[weekly batch] {len(pending_tickers)} ticker 增量更新"
                    f"（从 {pending_start} 到 {target_monday}）"
                )
                for i in range(0, len(pending_tickers), YF_BATCH_SIZE):
                    batch_pending = pending_tickers[i:i + YF_BATCH_SIZE]
                    _download_and_save_weekly(conn, batch_pending, pending_start, result)
                    if i + YF_BATCH_SIZE < len(pending_tickers):
                        delay = YF_BATCH_DELAY_BASE + random.uniform(
                            -YF_BATCH_DELAY_JITTER, YF_BATCH_DELAY_JITTER
                        )
                        time.sleep(delay)
            else:
                log.info(f"[weekly batch] 所有 ticker 已同步到 {target_monday}，无需更新")

        return result
    finally:
        conn.close()


def _download_and_save_weekly(
    conn,
    tickers: List[str],
    start_date: Optional[date],
    result: Dict[str, str],
) -> None:
    """下载一批 ticker 周线数据并保存到 prices_weekly。"""
    if not tickers:
        return

    if start_date is None:
        start_date = date.fromisoformat(START_DATE_US)

    target_monday = _last_us_weekly_date()
    end_dt = target_monday + timedelta(days=7)
    yf_symbols = [_yf_symbol(t) for t in tickers]

    log.info(f"[weekly batch] 下载 {len(tickers)} 只股票周线, {start_date} ~ {target_monday}")

    df = None
    last_exc = None
    for attempt in range(YF_RETRY_COUNT):
        try:
            signal.signal(signal.SIGINT, signal.SIG_DFL)
            df = yf.download(
                tickers=yf_symbols,
                start=start_date.strftime("%Y-%m-%d"),
                end=end_dt.strftime("%Y-%m-%d"),
                interval="1wk",
                group_by="ticker",
                auto_adjust=False,
                actions=False,
                threads=YF_THREADS,
                progress=False,
                timeout=YF_TIMEOUT,
                repair=False,
            )
            last_exc = None
            break
        except Exception as e:
            last_exc = e
            if attempt < YF_RETRY_COUNT - 1:
                backoff = 5 * (3 ** attempt)
                log.warning(f"yf.download weekly 第 {attempt+1} 次失败，{backoff}s 后重试: {e}")
                time.sleep(backoff)

    if last_exc is not None:
        msg = f"yfinance weekly failed after {YF_RETRY_COUNT} retries: {last_exc}"
        log.error(msg)
        for t in tickers:
            set_sync_error(conn, t, "price_weekly", msg)
            result[t] = f"error: {last_exc}"
        return

    top_level = set()
    if df is not None and not df.empty and isinstance(df.columns, pd.MultiIndex):
        top_level = set(df.columns.get_level_values(0))

    for t in tickers:
        yf_t = _yf_symbol(t)
        if yf_t not in top_level:
            log.warning(f"[{t}] yfinance weekly: ticker not in response")
            set_sync_error(conn, t, "price_weekly", "yfinance: ticker not in response")
            result[t] = "no_data"
            continue
        sub = df[yf_t]
        normalized = _normalize_weekly_frame(t, sub)
        if normalized.empty:
            log.warning(f"[{t}] yfinance weekly: empty frame")
            set_sync_error(conn, t, "price_weekly", "yfinance: empty frame")
            result[t] = "no_data"
            continue
        try:
            rows_inserted = _save_weekly_prices(conn, t, normalized)
            new_last = normalized["date"].max()
            set_sync_ok(conn, t, "price_weekly", new_last, rows_inserted)
            result[t] = "ok"
            log.info(f"[{t}] 周线写入 {rows_inserted} 条，最新={new_last}")
        except Exception as e:
            log.error(f"[{t}] 周线写库失败: {e}")
            set_sync_error(conn, t, "price_weekly", str(e))
            result[t] = f"error: {e}"


def _yf_symbol(ticker: str) -> str:
    """DB ticker → yfinance symbol (BRK.B → BRK-B)."""
    return ticker.upper().replace(".", "-")


def _normalize_weekly_frame(ticker: str, sub: pd.DataFrame) -> pd.DataFrame:
    """yfinance 单 ticker 周线子表 → [ticker, date, open, high, low, close, volume]"""
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


def _save_weekly_prices(conn, ticker: str, df: pd.DataFrame) -> int:
    """INSERT IGNORE 写 prices_weekly 表，UNIQUE KEY (ticker, date) 自动去重。"""
    sql = """
        INSERT IGNORE INTO prices_weekly (ticker, date, open, high, low, close, volume)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """
    rows = [
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
    with conn.cursor() as cur:
        cur.executemany(sql, rows)
    conn.commit()
    return len(rows)
```

- [ ] **Step 2: Run the tests**

```bash
uv run pytest tests/test_stock_updater_us_weekly.py -v
```

Expected: all 14 tests PASS.

- [ ] **Step 3: Commit**

```bash
git add data/stock_updater_us_weekly.py
git commit -m "feat: add stock_updater_us_weekly — weekly price ingest for US market"
```

---

## Task 3: Add `weekly()` to `market_us.py` and `weekly` subcommand to `main.py`

**Files:**
- Modify: `data/market_us.py` (append only — do not touch existing functions)
- Modify: `main.py` (append `cmd_weekly`, one new subparser, one new route)

- [ ] **Step 1: Append `weekly()` to `data/market_us.py`**

Open `data/market_us.py`. After the last function (`rebase`), append:

```python


def weekly(tickers: list[str] | None = None) -> dict[str, str]:
    """Pull weekly prices for US universe into prices_weekly."""
    from data import stock_updater_us_weekly
    targets = tickers or list_active_tickers()
    return stock_updater_us_weekly.update_weekly_batch(targets)
```

- [ ] **Step 2: Add `weekly` subparser to `main.py`**

In `_build_parser()`, after the `p_rebase` block and before `sub.add_parser("status", ...)`, add:

```python
    p_weekly = sub.add_parser("weekly", help="Run weekly ingest (US market)")
    p_weekly.add_argument("--market", choices=("us",), default="us")
    p_weekly.add_argument("--code", action="append", default=None,
                          help="Only this ticker (repeatable, debug aid)")
```

- [ ] **Step 3: Add `cmd_weekly()` function to `main.py`**

After `cmd_daily()` and before `cmd_rebase()`, add:

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

- [ ] **Step 4: Add routing in `main()`**

In `main()`, after `if args.cmd == "daily":` block, add:

```python
    if args.cmd == "weekly":
        return cmd_weekly(args.market, args.code)
```

- [ ] **Step 5: Run existing test suite to confirm nothing broken**

```bash
uv run pytest tests/ -v --ignore=tests/test_db_smoke.py -x 2>&1 | tail -20
```

Expected: all tests PASS (no regressions in daily ingest).

- [ ] **Step 6: Smoke-test CLI help**

```bash
uv run main.py weekly --help
```

Expected output includes:
```
usage: main.py weekly [-h] [--market {us}] [--code CODE]
Run weekly ingest (US market)
```

- [ ] **Step 7: Commit**

```bash
git add data/market_us.py main.py
git commit -m "feat: add weekly CLI subcommand for US market weekly price ingest"
```

---

## Task 4: Final verification

- [ ] **Step 1: Run full test suite**

```bash
uv run pytest tests/ -v --ignore=tests/test_db_smoke.py 2>&1 | tail -30
```

Expected: all tests PASS.

- [ ] **Step 2: Verify `prices_weekly` table exists in DB**

```bash
uv run python -c "
from db import query
rows = query('SHOW CREATE TABLE prices_weekly')
print(rows[0])
"
```

Expected: table definition printed without error.

- [ ] **Step 3: Done**

All tasks complete. `uv run main.py weekly --market us` is ready for cron scheduling alongside `daily`.

To add to cron (example — runs at 06:30 Beijing time, after US Friday close):
```bash
30 6 * * 6 /path/to/scripts/daily_update.sh weekly
```
Or simply add to the existing `daily_update.sh` as a parallel step.
