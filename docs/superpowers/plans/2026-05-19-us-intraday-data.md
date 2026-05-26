# US Intraday Data (15m / 1h) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为美股 SP500+Russell1000（~1016 只）添加 15 分钟和 1 小时 K 线，每日增量追加，长期积累完整历史。

**Architecture:** 新建独立模块 `data/intraday_updater_us.py`，复用 yfinance + 现有 `sync_log` 机制，数据写入新表 `prices_intraday`（PRIMARY KEY: ticker + interval + datetime）。CLI 新增 `intraday` 子命令。

**Tech Stack:** Python 3.12, yfinance, pymysql, pandas, argparse（与现有代码一致）

---

## File Structure

| 文件 | 操作 | 职责 |
|------|------|------|
| `db.py` | Modify | 新增 `create_prices_intraday_table()` |
| `data/intraday_updater_us.py` | Create | 核心拉取 + 写库逻辑 |
| `main.py` | Modify | 新增 `intraday` CLI 子命令 |
| `tests/test_intraday_updater_us.py` | Create | 单元测试 |

---

## Task 1: DB Migration — `prices_intraday` 表

**Files:**
- Modify: `db.py`
- Modify: `main.py`
- Test: `tests/test_intraday_updater_us.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_intraday_updater_us.py
from unittest.mock import patch


def test_create_prices_intraday_table_executes_ddl():
    with patch("db.execute") as mock_execute:
        from db import create_prices_intraday_table
        create_prices_intraday_table()
        mock_execute.assert_called_once()
        sql = mock_execute.call_args[0][0]
        assert "prices_intraday" in sql
        assert "CREATE TABLE IF NOT EXISTS" in sql
        assert "`interval`" in sql
```

- [ ] **Step 2: 运行确认失败**

```bash
uv run pytest tests/test_intraday_updater_us.py::test_create_prices_intraday_table_executes_ddl -v
```

期望：`ImportError` 或 `AttributeError: module 'db' has no attribute 'create_prices_intraday_table'`

- [ ] **Step 3: 在 `db.py` 末尾添加建表函数**

在 `db.py` 末尾（`show_status` 之后）追加：

```python
def create_prices_intraday_table() -> None:
    """Create prices_intraday table if not exists. Idempotent."""
    execute("""
        CREATE TABLE IF NOT EXISTS prices_intraday (
            ticker    VARCHAR(20)   NOT NULL,
            `interval` VARCHAR(4)  NOT NULL,
            datetime  DATETIME      NOT NULL,
            open      DECIMAL(12,4),
            high      DECIMAL(12,4),
            low       DECIMAL(12,4),
            close     DECIMAL(12,4),
            volume    BIGINT,
            PRIMARY KEY (ticker, `interval`, datetime),
            INDEX idx_interval_ticker (`interval`, ticker, datetime)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
```

- [ ] **Step 4: 运行确认通过**

```bash
uv run pytest tests/test_intraday_updater_us.py::test_create_prices_intraday_table_executes_ddl -v
```

期望：PASS

- [ ] **Step 5: 在 `main.py` 添加 `migrate-intraday` 子命令**

在 `_build_parser()` 中，`sub.add_parser("status", ...)` 之后添加：

```python
sub.add_parser("migrate-intraday", help="Create prices_intraday table (idempotent)")
```

在 `main()` 函数中，`if args.cmd == "status":` 之后添加：

```python
if args.cmd == "migrate-intraday":
    from db import create_prices_intraday_table
    create_prices_intraday_table()
    print("prices_intraday table ready")
    return 0
```

- [ ] **Step 6: 手动运行建表（需 DB 连接）**

```bash
uv run main.py migrate-intraday
```

期望输出：`prices_intraday table ready`

- [ ] **Step 7: Commit**

```bash
git add db.py main.py tests/test_intraday_updater_us.py
git commit -m "feat: add prices_intraday table migration"
```

---

## Task 2: `data/intraday_updater_us.py` — 核心模块

**Files:**
- Create: `data/intraday_updater_us.py`
- Test: `tests/test_intraday_updater_us.py`

### 2a: `_normalize_frame` 纯函数

- [ ] **Step 1: 写失败测试**

```python
# 追加到 tests/test_intraday_updater_us.py
import pandas as pd
from datetime import datetime, timezone


def test_normalize_frame_basic():
    """_normalize_frame 把 yfinance 子表转换为标准列。"""
    # yfinance intraday 返回 timezone-aware datetime index
    idx = pd.to_datetime([
        "2026-05-15 14:30:00+00:00",
        "2026-05-15 14:45:00+00:00",
    ])
    sub = pd.DataFrame({
        "Open":   [150.0, 151.0],
        "High":   [151.5, 152.0],
        "Low":    [149.5, 150.5],
        "Close":  [151.0, 151.5],
        "Volume": [1000000, 900000],
    }, index=idx)
    sub.index.name = "Datetime"

    from data.intraday_updater_us import _normalize_frame
    result = _normalize_frame("AAPL", "15m", sub)

    assert list(result.columns) == ["ticker", "interval", "datetime", "open", "high", "low", "close", "volume"]
    assert len(result) == 2
    assert result["ticker"].iloc[0] == "AAPL"
    assert result["interval"].iloc[0] == "15m"
    # datetime should be timezone-naive (stripped for MySQL)
    assert result["datetime"].dtype == "datetime64[ns]"
    assert result["datetime"].iloc[0].tzinfo is None
    assert result["close"].iloc[0] == 151.0


def test_normalize_frame_empty():
    from data.intraday_updater_us import _normalize_frame
    result = _normalize_frame("AAPL", "15m", pd.DataFrame())
    assert result.empty
    assert list(result.columns) == ["ticker", "interval", "datetime", "open", "high", "low", "close", "volume"]


def test_sync_type():
    from data.intraday_updater_us import _sync_type
    assert _sync_type("15m") == "intraday_15m"
    assert _sync_type("1h") == "intraday_60m"


def test_yf_symbol():
    from data.intraday_updater_us import _yf_symbol
    assert _yf_symbol("BRK.B") == "BRK-B"
    assert _yf_symbol("AAPL") == "AAPL"
```

注意：`_sync_type("1h")` 返回 `"intraday_60m"`，因为 yfinance 用 `60m`，sync_log 的 data_type 应与 yfinance interval 一致，避免混淆。

- [ ] **Step 2: 运行确认失败**

```bash
uv run pytest tests/test_intraday_updater_us.py -k "normalize or sync_type or yf_symbol" -v
```

期望：全部 `ImportError`

- [ ] **Step 3: 创建 `data/intraday_updater_us.py`，实现纯函数**

```python
"""
intraday_updater_us.py — 美股分钟级行情拉取（15m / 1h）

数据源: yfinance 免费 tier
存储: prices_intraday 表
Sync: sync_log data_type='intraday_15m'|'intraday_60m'
"""

from __future__ import annotations

import logging
import random
import signal
import time
from datetime import date, timedelta
from typing import Optional

import pandas as pd
import yfinance as yf

from config import (
    YF_BATCH_DELAY_BASE,
    YF_BATCH_DELAY_JITTER,
    YF_BATCH_SIZE,
    YF_RETRY_COUNT,
    YF_TIMEOUT,
)
from data.base import to_float, to_int
from db import get_conn, get_last_sync, set_sync_error, set_sync_ok

log = logging.getLogger(__name__)

# interval → yfinance 参数字符串
YF_INTERVAL_MAP: dict[str, str] = {
    "15m": "15m",
    "1h":  "60m",
}

# interval → yfinance 免费 tier 最大可拉天数
INTERVAL_LOOKBACK_DAYS: dict[str, int] = {
    "15m": 60,
    "1h":  730,
}

SUPPORTED_INTERVALS = list(YF_INTERVAL_MAP.keys())


def _sync_type(interval: str) -> str:
    """'15m' → 'intraday_15m', '1h' → 'intraday_60m'"""
    return f"intraday_{YF_INTERVAL_MAP[interval]}"


def _yf_symbol(ticker: str) -> str:
    """DB ticker → yfinance symbol: BRK.B → BRK-B"""
    return ticker.upper().replace(".", "-")


def _normalize_frame(ticker: str, interval: str, sub: pd.DataFrame) -> pd.DataFrame:
    """yfinance 单 ticker 子表 → 标准列 [ticker, interval, datetime, open, high, low, close, volume]"""
    cols = ["ticker", "interval", "datetime", "open", "high", "low", "close", "volume"]
    if sub is None or sub.empty:
        return pd.DataFrame(columns=cols)

    df = sub.reset_index()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df.columns = [str(c).lower() for c in df.columns]

    # rename datetime index column（yfinance 用 'datetime' 或 'date'）
    for cand in ("datetime", "date", "index"):
        if cand in df.columns:
            df = df.rename(columns={cand: "datetime"})
            break

    df["datetime"] = pd.to_datetime(df["datetime"])
    # 剥除时区，MySQL DATETIME 无时区（yfinance 返回 UTC）
    if df["datetime"].dt.tz is not None:
        df["datetime"] = df["datetime"].dt.tz_convert("UTC").dt.tz_localize(None)

    df["ticker"] = ticker
    df["interval"] = interval
    df = df.dropna(subset=["datetime", "close"])
    return df[cols].sort_values("datetime").reset_index(drop=True)
```

- [ ] **Step 4: 运行确认通过**

```bash
uv run pytest tests/test_intraday_updater_us.py -k "normalize or sync_type or yf_symbol" -v
```

期望：全部 PASS

- [ ] **Step 5: Commit**

```bash
git add data/intraday_updater_us.py tests/test_intraday_updater_us.py
git commit -m "feat: add intraday_updater_us pure functions"
```

### 2b: `_save_rows` 写库函数

- [ ] **Step 1: 写失败测试**

```python
# 追加到 tests/test_intraday_updater_us.py
from unittest.mock import MagicMock
from datetime import datetime


def test_save_rows_executes_insert():
    df = pd.DataFrame({
        "ticker":   ["AAPL", "AAPL"],
        "interval": ["15m", "15m"],
        "datetime": [datetime(2026, 5, 15, 14, 30), datetime(2026, 5, 15, 14, 45)],
        "open":     [150.0, 151.0],
        "high":     [151.5, 152.0],
        "low":      [149.5, 150.5],
        "close":    [151.0, 151.5],
        "volume":   [1000000, 900000],
    })
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__ = lambda s: mock_cursor
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

    from data.intraday_updater_us import _save_rows
    n = _save_rows(mock_conn, df)

    assert n == 2
    mock_cursor.executemany.assert_called_once()
    sql = mock_cursor.executemany.call_args[0][0]
    assert "INSERT IGNORE INTO prices_intraday" in sql
    assert "`interval`" in sql
    mock_conn.commit.assert_called_once()
```

- [ ] **Step 2: 运行确认失败**

```bash
uv run pytest tests/test_intraday_updater_us.py::test_save_rows_executes_insert -v
```

期望：`ImportError: cannot import name '_save_rows'`

- [ ] **Step 3: 在 `data/intraday_updater_us.py` 追加 `_save_rows`**

```python
def _save_rows(conn, df: pd.DataFrame) -> int:
    """INSERT IGNORE 写 prices_intraday，PRIMARY KEY 自动去重"""
    sql = """
        INSERT IGNORE INTO prices_intraday
          (ticker, `interval`, datetime, open, high, low, close, volume)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """
    rows = [
        (
            r.ticker,
            r.interval,
            r.datetime,
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

- [ ] **Step 4: 运行确认通过**

```bash
uv run pytest tests/test_intraday_updater_us.py::test_save_rows_executes_insert -v
```

期望：PASS

- [ ] **Step 5: Commit**

```bash
git add data/intraday_updater_us.py tests/test_intraday_updater_us.py
git commit -m "feat: add _save_rows to intraday_updater_us"
```

### 2c: `update_intraday` 主函数

- [ ] **Step 1: 写失败测试**

```python
# 追加到 tests/test_intraday_updater_us.py
from unittest.mock import patch, MagicMock, call
import pandas as pd
from datetime import date


def _make_yf_multiindex_df(symbol: str, interval: str) -> pd.DataFrame:
    """构造 yfinance 批量下载返回的 MultiIndex DataFrame"""
    import pandas as pd
    from datetime import datetime
    idx = pd.to_datetime([
        "2026-05-15 14:30:00+00:00",
        "2026-05-15 14:45:00+00:00",
    ])
    cols = pd.MultiIndex.from_tuples(
        [(col, symbol) for col in ["Open", "High", "Low", "Close", "Volume"]],
        names=["Price", "Ticker"],
    )
    data = {
        ("Open",   symbol): [150.0, 151.0],
        ("High",   symbol): [151.5, 152.0],
        ("Low",    symbol): [149.5, 150.5],
        ("Close",  symbol): [151.0, 151.5],
        ("Volume", symbol): [1000000, 900000],
    }
    df = pd.DataFrame(data, index=idx)
    df.columns = cols
    df.index.name = "Datetime"
    return df


@patch("data.intraday_updater_us.get_conn")
@patch("data.intraday_updater_us.get_last_sync")
@patch("data.intraday_updater_us.set_sync_ok")
@patch("data.intraday_updater_us.set_sync_error")
@patch("data.intraday_updater_us.yf.download")
@patch("data.market_us.list_active_tickers")
def test_update_intraday_calls_yf_download(
    mock_list, mock_yf_download, mock_set_error, mock_set_ok, mock_get_last_sync, mock_get_conn
):
    mock_list.return_value = ["AAPL"]
    mock_get_last_sync.return_value = None  # 首次：全量拉取
    mock_get_conn.return_value = MagicMock()

    mock_yf_download.return_value = _make_yf_multiindex_df("AAPL", "15m")

    with patch("data.intraday_updater_us._save_rows", return_value=2):
        from data.intraday_updater_us import update_intraday
        result = update_intraday("15m")

    assert result["AAPL"] == "ok"
    mock_yf_download.assert_called_once()
    call_kwargs = mock_yf_download.call_args
    assert call_kwargs[1]["interval"] == "15m"


@patch("data.intraday_updater_us.get_conn")
@patch("data.intraday_updater_us.get_last_sync")
@patch("data.market_us.list_active_tickers")
def test_update_intraday_skips_up_to_date_ticker(mock_list, mock_get_last_sync, mock_get_conn):
    mock_list.return_value = ["AAPL"]
    mock_get_last_sync.return_value = date.today()  # 已是最新
    mock_get_conn.return_value = MagicMock()

    with patch("data.intraday_updater_us.yf.download") as mock_dl:
        from data.intraday_updater_us import update_intraday
        result = update_intraday("15m")

    assert result["AAPL"] == "ok"
    mock_dl.assert_not_called()


def test_update_intraday_rejects_unsupported_interval():
    from data.intraday_updater_us import update_intraday
    import pytest
    with pytest.raises(ValueError, match="Unsupported interval"):
        update_intraday("3m")
```

- [ ] **Step 2: 运行确认失败**

```bash
uv run pytest tests/test_intraday_updater_us.py -k "update_intraday" -v
```

期望：`ImportError: cannot import name 'update_intraday'`

- [ ] **Step 3: 在 `data/intraday_updater_us.py` 追加 `_download_and_save` 和 `update_intraday`**

```python
def update_intraday(interval: str) -> dict[str, str]:
    """批量增量拉取美股 intraday，写入 prices_intraday。

    Args:
        interval: '15m' 或 '1h'
    Returns:
        {ticker: 'ok' | 'no_data' | 'error: <msg>'}
    """
    if interval not in SUPPORTED_INTERVALS:
        raise ValueError(f"Unsupported interval: {interval}. Supported: {SUPPORTED_INTERVALS}")

    from data.market_us import list_active_tickers
    tickers = list_active_tickers()

    lookback_days = INTERVAL_LOOKBACK_DAYS[interval]
    floor_date = date.today() - timedelta(days=lookback_days - 1)
    today = date.today()

    result: dict[str, str] = {}
    conn = get_conn()
    try:
        sync_type = _sync_type(interval)

        # 分类 ticker：需要更新的及其起始日期
        pending: list[tuple[str, date]] = []
        for t in tickers:
            last = get_last_sync(conn, t, sync_type)
            if last is None:
                pending.append((t, floor_date))
            elif last >= today:
                result[t] = "ok"
            else:
                start = max(last + timedelta(days=1), floor_date)
                pending.append((t, start))

        if not pending:
            log.info(f"[intraday {interval}] 所有 ticker 已是最新，无需更新")
            return result

        log.info(f"[intraday {interval}] 需更新 {len(pending)} 只 ticker")

        # 按 start_date 排序，同批取最早起点（INSERT IGNORE 保证幂等）
        pending.sort(key=lambda x: x[1])

        for i in range(0, len(pending), YF_BATCH_SIZE):
            batch_pairs = pending[i:i + YF_BATCH_SIZE]
            batch = [t for t, _ in batch_pairs]
            batch_start = min(s for _, s in batch_pairs)
            _download_and_save(conn, batch, interval, batch_start, result)
            if i + YF_BATCH_SIZE < len(pending):
                delay = YF_BATCH_DELAY_BASE + random.uniform(
                    -YF_BATCH_DELAY_JITTER, YF_BATCH_DELAY_JITTER
                )
                log.debug(f"[intraday {interval}] 等待 {delay:.1f}s")
                time.sleep(delay)

        return result
    finally:
        conn.close()


def _download_and_save(
    conn,
    tickers: list[str],
    interval: str,
    start_date: date,
    result: dict[str, str],
) -> None:
    """下载一批 ticker 的 intraday 数据并保存到 prices_intraday。"""
    end_date = date.today() + timedelta(days=1)
    yf_interval = YF_INTERVAL_MAP[interval]
    yf_symbols = [_yf_symbol(t) for t in tickers]
    sync_type = _sync_type(interval)

    log.info(f"[intraday {interval}] 下载 {len(tickers)} 只，{start_date} ~ {date.today()}")

    df = None
    last_exc: Optional[Exception] = None
    for attempt in range(YF_RETRY_COUNT):
        try:
            signal.signal(signal.SIGINT, signal.SIG_DFL)
            df = yf.download(
                tickers=yf_symbols,
                start=start_date.strftime("%Y-%m-%d"),
                end=end_date.strftime("%Y-%m-%d"),
                interval=yf_interval,
                group_by="ticker",
                auto_adjust=False,
                actions=False,
                threads=False,
                progress=False,
                timeout=YF_TIMEOUT,
            )
            last_exc = None
            break
        except Exception as e:
            last_exc = e
            if attempt < YF_RETRY_COUNT - 1:
                backoff = 5 * (3 ** attempt)
                log.warning(f"yf.download attempt {attempt + 1} failed, retry in {backoff}s: {e}")
                time.sleep(backoff)

    if last_exc is not None:
        msg = f"yfinance failed after {YF_RETRY_COUNT} retries: {last_exc}"
        log.error(msg)
        for t in tickers:
            set_sync_error(conn, t, sync_type, msg)
            result[t] = f"error: {last_exc}"
        return

    # yfinance: 2+ tickers → MultiIndex DataFrame; single ticker → plain DataFrame
    is_multi = df is not None and not df.empty and isinstance(df.columns, pd.MultiIndex)
    top_level = set(df.columns.get_level_values(0)) if is_multi else set()

    for t in tickers:
        yf_t = _yf_symbol(t)
        if is_multi:
            if yf_t not in top_level:
                log.warning(f"[{t}] not in yfinance response")
                set_sync_error(conn, t, sync_type, "yfinance: ticker not in response")
                result[t] = "no_data"
                continue
            sub = df[yf_t]
        elif df is not None and not df.empty and len(tickers) == 1:
            sub = df  # single-ticker: plain DataFrame
        else:
            log.warning(f"[{t}] no data in response")
            set_sync_error(conn, t, sync_type, "yfinance: empty or unexpected response")
            result[t] = "no_data"
            continue
        normalized = _normalize_frame(t, interval, sub)
        if normalized.empty:
            log.warning(f"[{t}] empty frame")
            set_sync_error(conn, t, sync_type, "yfinance: empty frame")
            result[t] = "no_data"
            continue
        try:
            rows_inserted = _save_rows(conn, normalized)
            new_last = normalized["datetime"].max().date()
            set_sync_ok(conn, t, sync_type, new_last, rows_inserted)
            result[t] = "ok"
            log.info(f"[{t}] 写入 {rows_inserted} 条，最新={new_last}")
        except Exception as e:
            log.error(f"[{t}] 写库失败: {e}")
            set_sync_error(conn, t, sync_type, str(e))
            result[t] = f"error: {e}"
```

- [ ] **Step 4: 运行确认通过**

```bash
uv run pytest tests/test_intraday_updater_us.py -k "update_intraday" -v
```

期望：全部 PASS

- [ ] **Step 5: 运行所有 intraday 测试**

```bash
uv run pytest tests/test_intraday_updater_us.py -v
```

期望：全部 PASS

- [ ] **Step 6: Commit**

```bash
git add data/intraday_updater_us.py tests/test_intraday_updater_us.py
git commit -m "feat: implement update_intraday in intraday_updater_us"
```

---

## Task 3: `main.py` — `intraday` CLI 子命令

**Files:**
- Modify: `main.py`

- [ ] **Step 1: 写失败测试**

```python
# 追加到 tests/test_intraday_updater_us.py
from unittest.mock import patch


def test_cli_intraday_all(capsys):
    with patch("data.intraday_updater_us.update_intraday") as mock_update:
        mock_update.return_value = {"AAPL": "ok"}
        import main
        ret = main.main(["intraday"])
    assert ret == 0
    assert mock_update.call_count == 2  # 15m 和 1h 各调一次
    intervals_called = [c.args[0] for c in mock_update.call_args_list]
    assert "15m" in intervals_called
    assert "1h" in intervals_called


def test_cli_intraday_single_interval(capsys):
    with patch("data.intraday_updater_us.update_intraday") as mock_update:
        mock_update.return_value = {"AAPL": "ok"}
        import main
        ret = main.main(["intraday", "--interval", "15m"])
    assert ret == 0
    mock_update.assert_called_once_with("15m")
```

- [ ] **Step 2: 运行确认失败**

```bash
uv run pytest tests/test_intraday_updater_us.py -k "cli_intraday" -v
```

期望：`SystemExit` 或 `error: argument cmd: invalid choice: 'intraday'`

- [ ] **Step 3: 在 `main.py` 的 `_build_parser()` 中添加 `intraday` 子命令**

在 `p_ts = sub.add_parser("tushare-backfill", ...)` 之后追加：

```python
p_intraday = sub.add_parser("intraday", help="拉取美股分钟级行情（15m / 1h）并写入 prices_intraday")
p_intraday.add_argument(
    "--interval",
    choices=["15m", "1h"],
    default=None,
    help="仅拉取指定 interval（默认：15m 和 1h 均拉）",
)
```

- [ ] **Step 4: 在 `main.py` 添加 `cmd_intraday` 函数**

在 `cmd_tushare_backfill` 之后、`_import_market` 之前追加：

```python
def cmd_intraday(interval: str | None) -> int:
    from data.intraday_updater_us import update_intraday, SUPPORTED_INTERVALS
    intervals = [interval] if interval else SUPPORTED_INTERVALS
    for ivl in intervals:
        log.info(f"[intraday] 开始拉取 {ivl}")
        result = update_intraday(ivl)
        ok = sum(1 for v in result.values() if v == "ok")
        err = sum(1 for v in result.values() if v.startswith("error"))
        log.info(f"[intraday {ivl}] 完成: ok={ok}, error={err}")
    return 0
```

- [ ] **Step 5: 在 `main()` 中路由 `intraday` 命令**

在 `if args.cmd == "tushare-backfill":` 之后追加：

```python
if args.cmd == "intraday":
    return cmd_intraday(args.interval)
```

- [ ] **Step 6: 运行确认通过**

```bash
uv run pytest tests/test_intraday_updater_us.py -k "cli_intraday" -v
```

期望：全部 PASS

- [ ] **Step 7: 运行全量测试确认无回归**

```bash
uv run pytest tests/ -v --ignore=tests/test_db_smoke.py
```

期望：全部 PASS（`test_db_smoke.py` 需真实 DB 连接，跳过）

- [ ] **Step 8: Commit**

```bash
git add main.py tests/test_intraday_updater_us.py
git commit -m "feat: add intraday CLI command to main.py"
```

---

## Task 4: 端到端验证（需真实 DB + 网络）

- [ ] **Step 1: 建表**

```bash
uv run main.py migrate-intraday
```

期望：`prices_intraday table ready`

- [ ] **Step 2: 小范围测试（单只 ticker，1h interval）**

临时在 shell 中测试单只：

```bash
uv run python -c "
from data.intraday_updater_us import _download_and_save, _sync_type
from db import get_conn

conn = get_conn()
result = {}
from datetime import date, timedelta
start = date.today() - timedelta(days=30)
_download_and_save(conn, ['AAPL'], '1h', start, result)
conn.close()
print(result)
"
```

期望：`{'AAPL': 'ok'}`，DB 中 `prices_intraday` 有 AAPL 的 1h 数据

- [ ] **Step 3: 验证 DB 数据**

```bash
uv run python -c "
from db import query
rows = query(\"SELECT COUNT(*), MIN(datetime), MAX(datetime) FROM prices_intraday WHERE ticker='AAPL' AND \`interval\`='60m'\")
print(rows)
"
```

期望：有数据，datetime 范围合理

- [ ] **Step 4: 运行完整 1h 拉取**

```bash
uv run main.py intraday --interval 1h
```

监控日志，确认无大量 error。

- [ ] **Step 5: 运行完整 15m 拉取**

```bash
uv run main.py intraday --interval 15m
```

- [ ] **Step 6: 验证幂等性（重复运行不增加行数）**

```bash
uv run python -c "
from db import query
r1 = query('SELECT COUNT(*) as n FROM prices_intraday')
print('before:', r1[0]['n'])
"
uv run main.py intraday --interval 1h
uv run python -c "
from db import query
r2 = query('SELECT COUNT(*) as n FROM prices_intraday')
print('after:', r2[0]['n'])
"
```

期望：两次 COUNT 相同（INSERT IGNORE 去重）

- [ ] **Step 7: Final commit**

```bash
git add .
git commit -m "feat: US intraday data (15m/1h) complete"
```

---

## 验证清单（Spec Coverage）

| Spec 需求 | 对应 Task |
|-----------|----------|
| 15m + 1h 两个 interval | Task 2 `SUPPORTED_INTERVALS` |
| yfinance 免费 tier | Task 2 `YF_INTERVAL_MAP` |
| 15m=60天, 1h=730天上限 | Task 2 `INTERVAL_LOOKBACK_DAYS` |
| `prices_intraday` 新表 | Task 1 DDL |
| `sync_log` 复用 | Task 2 `_sync_type` → `set_sync_ok/error` |
| 每日增量追加 | Task 2 `update_intraday` 增量逻辑 |
| INSERT IGNORE 幂等 | Task 2 `_save_rows` |
| CLI `intraday [--interval]` | Task 3 |
| 不加 cron | ✓ 无调度相关代码 |
