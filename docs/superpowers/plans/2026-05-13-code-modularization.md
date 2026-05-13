# 代码模块化重构实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 提取重复代码到共享模块，删除死代码，修复安全问题

**Architecture:** 创建 data/index_base.py 提取index updater共享函数，扩展 db.py 添加缺失helpers，重构scripts使用现有模块，删除无用代码

**Tech Stack:** Python 3.12+, pymysql, akshare, yfinance

---

## 文件结构

**创建：**
- `data/index_base.py` - index updater共享helpers

**修改：**
- `db.py` - 添加 get_latest_snapshot_tickers
- `data/index_updater_us.py` - 使用 index_base.py
- `data/index_updater_cn.py` - 使用 index_base.py
- `data/index_updater_hk.py` - 使用 index_base.py
- `data/market_us.py` - 使用 db.py
- `data/market_hk.py` - 使用 db.py
- `data/stock_updater_us.py` - 删除死代码
- `scripts/backfill_sp500_yfinance.py` - 使用 db.py/config.py
- `scripts/backfill_hk_yfinance.py` - 使用 db.py/config.py

**删除：**
- `scripts/clear_sp500_sync.py` - 硬编码密码，不安全

---

### Task 1: 创建 data/index_base.py 共享模块

**Files:**
- Create: `data/index_base.py`
- Test: `tests/test_index_base.py`

- [ ] **Step 1: 写 index_base.py 共享函数**

```python
"""Index updater shared helpers.

Used by index_updater_us, index_updater_cn, index_updater_hk.
"""

from __future__ import annotations

from datetime import date
from typing import Optional, Set, Tuple
import pandas as pd

from db import get_conn


def get_last_snapshot_date(conn, index_id: str) -> Optional[date]:
    """获取上一次快照日期"""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT MAX(snapshot_date) FROM index_constituents WHERE index_id = %s",
            (index_id,),
        )
        result = cur.fetchone()
        return result[0] if result else None


def save_snapshot(conn, df: pd.DataFrame, index_id: str, snap_date: date) -> int:
    """保存成分股快照到 index_constituents 表"""
    rows = [
        (
            index_id,
            snap_date,
            r["ticker"],
            r.get("name", None),
            r.get("sector", None),
        )
        for _, r in df.iterrows()
    ]

    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT IGNORE INTO index_constituents
                (index_id, snapshot_date, ticker, name, sector)
            VALUES (%s, %s, %s, %s, %s)
            """,
            rows,
        )
        inserted = cur.rowcount

    conn.commit()
    return inserted


def detect_and_record_changes(
    conn,
    index_id: str,
    new_date: date,
    new_tickers: Set[str],
    prev_date: Optional[date],
) -> Tuple[int, int]:
    """
    检测成分股变动并记录到 constituent_changes 表

    Returns:
        (added_count, removed_count)
    """
    if not prev_date:
        # First-ever snapshot: mark all as ADDED
        rows = [(index_id, t, "", "ADDED", new_date, None) for t in new_tickers]
        with conn.cursor() as cur:
            cur.executemany(
                """
                INSERT IGNORE INTO constituent_changes
                    (index_id, ticker, name, change_type, change_date, prev_date)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                rows,
            )
        conn.commit()
        return len(rows), 0

    # 获取上次成分股
    with conn.cursor() as cur:
        cur.execute(
            "SELECT ticker FROM index_constituents "
            "WHERE index_id = %s AND snapshot_date = %s",
            (index_id, prev_date),
        )
        prev_tickers = {r[0] for r in cur.fetchall()}

    if not prev_tickers:
        return 0, 0

    # 计算变动
    added = new_tickers - prev_tickers
    removed = prev_tickers - new_tickers

    # 记录变动
    if added or removed:
        rows = (
            [(index_id, t, "", "ADDED", new_date, prev_date) for t in added]
            + [(index_id, t, "", "REMOVED", new_date, prev_date) for t in removed]
        )
        with conn.cursor() as cur:
            cur.executemany(
                """
                INSERT IGNORE INTO constituent_changes
                    (index_id, ticker, name, change_type, change_date, prev_date)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                rows,
            )
        conn.commit()

    return len(added), len(removed)


def register_stocks(conn, df: pd.DataFrame, exchange: str = None) -> None:
    """将成分股基本信息写入 stocks 表

    Args:
        exchange: US market不传，CN/HK传交易所代码
    """
    rows = []
    for _, r in df.iterrows():
        ticker = r["ticker"]
        name = r.get("name", None)
        sector = r.get("sector", None)
        if exchange:
            rows.append((ticker, name, sector, exchange))
        else:
            rows.append((ticker, name, sector))

    with conn.cursor() as cur:
        if exchange:
            cur.executemany(
                """
                INSERT INTO stocks (ticker, name, gics_sector, exchange)
                VALUES (%s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    name = COALESCE(VALUES(name), name),
                    gics_sector = COALESCE(VALUES(gics_sector), gics_sector),
                    exchange = VALUES(exchange)
                """,
                rows,
            )
        else:
            cur.executemany(
                """
                INSERT INTO stocks (ticker, name, gics_sector)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    name = COALESCE(VALUES(name), name),
                    gics_sector = COALESCE(VALUES(gics_sector), gics_sector)
                """,
                rows,
            )
    conn.commit()


def upsert_index_log(
    conn,
    index_id: str,
    snap_date: date,
    rows: int,
    added: int,
    removed: int,
    status: str = "ok",
    msg: str = "",
) -> None:
    """更新 index_sync_log 表"""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO index_sync_log
                (index_id, snapshot_date, rows_added, added_count, removed_count, status, message)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                snapshot_date = VALUES(snapshot_date),
                last_run = CURRENT_TIMESTAMP,
                rows_added = VALUES(rows_added),
                added_count = VALUES(added_count),
                removed_count = VALUES(removed_count),
                status = VALUES(status),
                message = VALUES(message)
            """,
            (index_id, snap_date, rows, added, removed, status, msg),
        )
    conn.commit()
```

- [ ] **Step 2: 验证语法正确**

Run: `python -m py_compile data/index_base.py`
Expected: 无输出（成功）

- [ ] **Step 3: Commit**

```bash
git add data/index_base.py
git commit -m "refactor: 创建 index_base.py 共享helpers"
```

---

### Task 2: 扩展 db.py 添加 get_latest_snapshot_tickers

**Files:**
- Modify: `db.py:124-135`

- [ ] **Step 1: 在 db.py 添加新函数**

在 `get_index_tickers` 函数后添加：

```python
def get_latest_snapshot_tickers(index_id: str) -> list[str]:
    """获取指数最新快照的成分股ticker列表"""
    rows = query("""
        SELECT DISTINCT ticker FROM index_constituents
        WHERE index_id = %s
        AND snapshot_date = (
            SELECT MAX(snapshot_date) FROM index_constituents WHERE index_id = %s
        )
        ORDER BY ticker
    """, (index_id, index_id))
    return [r["ticker"] for r in rows]
```

- [ ] **Step 2: 验证语法**

Run: `python -m py_compile db.py`
Expected: 无输出

- [ ] **Step 3: Commit**

```bash
git add db.py
git commit -m "refactor: db.py 添加 get_latest_snapshot_tickers"
```

---

### Task 3: 重构 data/index_updater_us.py

**Files:**
- Modify: `data/index_updater_us.py` - 全文件重构

- [ ] **Step 1: 重写 index_updater_us.py 使用 index_base**

```python
"""
index_updater_us.py — SP500 指数成分股更新

数据源：
  SP500 → GitHub datasets (含 CIK，直接可用)
"""

import pandas as pd
import logging
from io import StringIO
from datetime import date

from config import INDEX_DELAY
from db import get_conn
from data.base import fetch_urls_sequentially, format_cik
from data.index_base import (
    get_last_snapshot_date,
    save_snapshot,
    detect_and_record_changes,
    register_stocks,
    upsert_index_log,
)

log = logging.getLogger(__name__)

# SP500 数据源（按优先级排序）
SP500_URLS = [
    "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv",
    "https://datahub.io/core/s-and-p-500-companies/r/constituents.csv",
]


def update_sp500() -> None:
    """更新 SP500 指数成分股快照"""
    index_id = "SP500"
    conn = get_conn()

    try:
        prev_date = get_last_snapshot_date(conn, index_id)

        if prev_date == date.today():
            log.info(f"[{index_id}] 今日已更新，跳过")
            return

        df = _fetch_sp500_data()

        if df is None or df.empty:
            log.error(f"[{index_id}] 获取数据失败")
            upsert_index_log(conn, index_id, date.today(), 0, 0, 0, "error", "无数据")
            return

        snap_date = date.today()
        new_tickers = set(df["ticker"].unique())

        inserted = save_snapshot(conn, df, index_id, snap_date)
        added, removed = detect_and_record_changes(conn, index_id, snap_date, new_tickers, prev_date)
        register_stocks(conn, df)
        upsert_index_log(conn, index_id, snap_date, inserted, added, removed)

        log.info(f"[{index_id}] 完成 {snap_date}: {inserted}条 +{added}加入 -{removed}退出")

    except Exception as e:
        log.error(f"[{index_id}] 更新失败: {e}")
        upsert_index_log(conn, index_id, date.today(), 0, 0, 0, "error", str(e))
    finally:
        conn.close()


def _fetch_sp500_data() -> pd.DataFrame:
    """从 GitHub/datahub 获取 SP500 成分股列表"""
    resp = fetch_urls_sequentially(SP500_URLS, context="SP500")

    if resp is None:
        return None

    df = pd.read_csv(StringIO(resp.text))

    # 标准化列名
    col_map = {
        "Symbol": "ticker",
        "Security": "name",
        "GICS Sector": "sector",
        "CIK": "cik",
        "Date added": "date_added",
    }
    df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})

    # 清洗数据
    df = df[df["ticker"].notna()]
    df["ticker"] = df["ticker"].str.strip().str.upper()

    # 格式化 CIK
    if "cik" in df.columns:
        df["cik"] = df["cik"].apply(format_cik)

    # 添加元数据
    df["index_id"] = "SP500"
    df["snapshot_date"] = date.today()

    log.info(f"[SP500] 获取 {len(df)} 只成分股")

    return df
```

- [ ] **Step 2: 验证语法**

Run: `python -m py_compile data/index_updater_us.py`
Expected: 无输出

- [ ] **Step 3: Commit**

```bash
git add data/index_updater_us.py
git commit -m "refactor: index_updater_us.py 使用 index_base.py"
```

---

### Task 4: 重构 data/index_updater_cn.py

**Files:**
- Modify: `data/index_updater_cn.py` - 全文件重构

- [ ] **Step 1: 重写 index_updater_cn.py 使用 index_base**

```python
"""CSI800 (中证800) constituent updater via akshare."""

from __future__ import annotations

import logging
from datetime import date

import akshare as ak
import pandas as pd

from db import get_conn
from data.ticker_utils import from_akshare_a
from data.index_base import (
    get_last_snapshot_date,
    save_snapshot,
    detect_and_record_changes,
    register_stocks,
    upsert_index_log,
)

log = logging.getLogger(__name__)

INDEX_ID = "CSI800"
AK_SYMBOL = "000906"


def update_csi800() -> None:
    conn = get_conn()
    try:
        prev_date = get_last_snapshot_date(conn, INDEX_ID)
        if prev_date == date.today():
            log.info(f"[{INDEX_ID}] 今日已更新，跳过")
            return

        df = _fetch_csi800()
        if df is None or df.empty:
            log.error(f"[{INDEX_ID}] 获取数据失败")
            upsert_index_log(conn, INDEX_ID, date.today(), 0, 0, 0, "error", "无数据")
            return

        snap = date.today()
        new_set = set(df["ticker"].unique())
        inserted = save_snapshot(conn, df, INDEX_ID, snap)
        added, removed = detect_and_record_changes(conn, INDEX_ID, snap, new_set, prev_date)

        # CN market 需要传 exchange
        register_stocks(conn, df, exchange=None)

        upsert_index_log(conn, INDEX_ID, snap, inserted, added, removed)
        log.info(f"[{INDEX_ID}] 完成 {snap}: {inserted}条 +{added} -{removed}")
    except Exception as e:
        log.error(f"[{INDEX_ID}] 更新失败: {e}")
        upsert_index_log(conn, INDEX_ID, date.today(), 0, 0, 0, "error", str(e))
    finally:
        conn.close()


def _fetch_csi800() -> pd.DataFrame:
    raw = ak.index_stock_cons_csindex(symbol=AK_SYMBOL)
    df = pd.DataFrame({
        "ticker": [from_akshare_a(c) for c in raw["成分券代码"].astype(str).str.zfill(6)],
        "name":   raw["成分券名称"],
        "sector": raw.get("行业", ""),
    })
    return df
```

- [ ] **Step 2: 验证语法**

Run: `python -m py_compile data/index_updater_cn.py`
Expected: 无输出

- [ ] **Step 3: Commit**

```bash
git add data/index_updater_cn.py
git commit -m "refactor: index_updater_cn.py 使用 index_base.py"
```

---

### Task 5: 重构 data/index_updater_hk.py

**Files:**
- Modify: `data/index_updater_hk.py` - 全文件重构

- [ ] **Step 1: 重写 index_updater_hk.py 使用 index_base**

```python
"""HSI (恒生指数) constituent updater via akshare."""

from __future__ import annotations

import logging
from datetime import date

import akshare as ak
import pandas as pd

from db import get_conn
from data.ticker_utils import from_akshare_hk
from data.index_base import (
    get_last_snapshot_date,
    save_snapshot,
    detect_and_record_changes,
    register_stocks,
    upsert_index_log,
)

log = logging.getLogger(__name__)

INDEX_ID = "HSI"
AK_SYMBOL = "HSI"


def update_hsi() -> None:
    conn = get_conn()
    try:
        prev_date = get_last_snapshot_date(conn, INDEX_ID)
        if prev_date == date.today():
            log.info(f"[{INDEX_ID}] 今日已更新，跳过")
            return

        df = _fetch_hsi()
        if df is None or df.empty:
            log.error(f"[{INDEX_ID}] 获取数据失败")
            upsert_index_log(conn, INDEX_ID, date.today(), 0, 0, 0, "error", "无数据")
            return

        snap = date.today()
        new_set = set(df["ticker"].unique())
        inserted = save_snapshot(conn, df, INDEX_ID, snap)
        added, removed = detect_and_record_changes(conn, INDEX_ID, snap, new_set, prev_date)
        register_stocks(conn, df, exchange="HK")
        upsert_index_log(conn, INDEX_ID, snap, inserted, added, removed)
        log.info(f"[{INDEX_ID}] 完成 {snap}: {inserted}条 +{added} -{removed}")
    except Exception as e:
        log.error(f"[{INDEX_ID}] 更新失败: {e}")
        upsert_index_log(conn, INDEX_ID, date.today(), 0, 0, 0, "error", str(e))
    finally:
        conn.close()


def _fetch_hsi() -> pd.DataFrame:
    raw = ak.index_stock_cons(symbol="HSI")
    df = pd.DataFrame({
        "ticker": [from_akshare_hk(str(c).zfill(5)) for c in raw["品种代码"]],
        "name":   raw["品种名称"],
        "sector": raw.get("行业", ""),
    })
    return df
```

- [ ] **Step 2: 验证语法**

Run: `python -m py_compile data/index_updater_hk.py`
Expected: 无输出

- [ ] **Step 3: Commit**

```bash
git add data/index_updater_hk.py
git commit -m "refactor: index_updater_hk.py 使用 index_base.py"
```

---

### Task 6: 重构 data/market_us.py 使用 db.py

**Files:**
- Modify: `data/market_us.py:102-111` - 删除私有函数，改用 db.py

- [ ] **Step 1: 删除 _latest_snapshot_tickers 函数，改用 db.py**

删除 `data/market_us.py` 中 `_latest_snapshot_tickers` 函数定义（102-111行）。

修改 import：
```python
from db import get_conn, get_index_tickers, get_latest_snapshot_tickers, query, execute
```

修改 `update_index` 函数：
```python
def update_index() -> tuple[list[str], int, int]:
    """Run SP500 snapshot + change detection. Returns (new_added_tickers, inserted, removed)."""
    prev_tickers = set(get_latest_snapshot_tickers("SP500"))

    index_updater_us.update_sp500()

    curr_tickers = set(get_latest_snapshot_tickers("SP500"))

    new_added = sorted(curr_tickers - prev_tickers)
    removed = len(prev_tickers - curr_tickers)
    return new_added, len(curr_tickers), removed
```

- [ ] **Step 2: 验证语法**

Run: `python -m py_compile data/market_us.py`
Expected: 无输出

- [ ] **Step 3: Commit**

```bash
git add data/market_us.py
git commit -m "refactor: market_us.py 使用 db.get_latest_snapshot_tickers"
```

---

### Task 7: 重构 data/market_hk.py 使用 db.py

**Files:**
- Modify: `data/market_hk.py:64-72` - 删除私有函数，改用 db.py

- [ ] **Step 1: 删除 _latest_snapshot_tickers 函数，改用 db.py**

删除 `data/market_hk.py` 中 `_latest_snapshot_tickers` 函数定义（64-72行）。

修改 import：
```python
from db import get_conn, get_index_tickers, get_latest_snapshot_tickers, query, execute
```

修改 `update_index` 函数：
```python
def update_index() -> tuple[list[str], int, int]:
    prev = set(get_latest_snapshot_tickers("HSI"))

    index_updater_hk.update_hsi()

    curr = set(get_latest_snapshot_tickers("HSI"))
    new_added = sorted(curr - prev)
    return new_added, len(curr), len(prev - curr)
```

- [ ] **Step 2: 验证语法**

Run: `python -m py_compile data/market_hk.py`
Expected: 无输出

- [ ] **Step 3: Commit**

```bash
git add data/market_hk.py
git commit -m "refactor: market_hk.py 使用 db.get_latest_snapshot_tickers"
```

---

### Task 8: 删除 data/stock_updater_us.py 死代码

**Files:**
- Modify: `data/stock_updater_us.py` - 删除无用函数

- [ ] **Step 1: 删除以下函数和代码**

删除：
- 行 80-88: `update_prices` 单ticker包装函数
- 行 310-312: `_yf_symbol` 函数（保留，但删除377-378的别名）
- 行 366-378: `guess_yf_ticker` 函数和 `guess_stooq_ticker` 别名

修改 `_download_and_save` 函数内部，`_yf_symbol` 已定义在行310-312，不需要删除。

- [ ] **Step 2: 验证语法**

Run: `python -m py_compile data/stock_updater_us.py`
Expected: 无输出

- [ ] **Step 3: Commit**

```bash
git add data/stock_updater_us.py
git commit -m "refactor: 删除 stock_updater_us.py 死代码"
```

---

### Task 9: 重构 scripts/backfill_sp500_yfinance.py

**Files:**
- Modify: `scripts/backfill_sp500_yfinance.py` - 使用 db.py/config.py

- [ ] **Step 1: 重写 scripts/backfill_sp500_yfinance.py**

```python
#!/usr/bin/env python3
"""SP500 backfill via yfinance - 使用 db.py 和 config.py"""

import yfinance as yf
import time
import pandas as pd
import logging
from datetime import date, datetime, timedelta
from typing import Dict

from db import get_conn, get_last_sync, set_sync_ok, set_sync_error
from config import DB, YF_RETRY_COUNT, YF_TIMEOUT, HISTORY_YEARS_US
from data.stock_updater_us import _yf_symbol, _normalize_yf_frame, _save_prices

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
log = logging.getLogger(__name__)

conn = get_conn()

# Get SP500 tickers
with conn.cursor() as cur:
    cur.execute("SELECT DISTINCT ticker FROM index_constituents WHERE index_id='SP500' ORDER BY ticker")
    tickers = [r[0] for r in cur.fetchall()]

log.info(f'SP500: {len(tickers)} tickers')

YF_BATCH_SIZE = 20
YF_BATCH_DELAY = 2.0
YF_LOOKBACK_DAYS = 7


def update_prices_batch(tickers, full_rebase=False) -> Dict[str, str]:
    if not tickers:
        return {}

    START_DATE = date(2010, 1, 1)
    per_ticker_start = {}
    for t in tickers:
        if full_rebase:
            start_dt = START_DATE
        else:
            last = get_last_sync(conn, t, "price")
            if last is None:
                start_dt = (datetime.today() - timedelta(days=365 * HISTORY_YEARS_US)).date()
            else:
                start_dt = last - timedelta(days=YF_LOOKBACK_DAYS)
        per_ticker_start[t] = start_dt

    batch_start = min(per_ticker_start.values())
    end_dt = (datetime.today() + timedelta(days=1)).date()
    yf_symbols = [_yf_symbol(t) for t in tickers]

    log.info(f"Batch: {batch_start} → {end_dt}, {len(tickers)} tickers")

    df = None
    last_exc = None
    for attempt in range(YF_RETRY_COUNT):
        try:
            df = yf.download(
                tickers=yf_symbols,
                start=batch_start.strftime("%Y-%m-%d"),
                end=end_dt.strftime("%Y-%m-%d"),
                interval="1d",
                group_by="ticker",
                auto_adjust=False,
                actions=False,
                threads=True,
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
                log.warning(f"yf.download 第 {attempt+1} 次失败，{backoff}s 后重试: {e}")
                time.sleep(backoff)

    result = {}
    if last_exc is not None:
        log.error(f"yfinance batch failed after {YF_RETRY_COUNT} retries: {last_exc}")
        for t in tickers:
            set_sync_error(conn, t, "price", str(last_exc))
            result[t] = f"error: {last_exc}"
        return result

    top_level = set()
    if df is not None and not df.empty and isinstance(df.columns, pd.MultiIndex):
        top_level = set(df.columns.get_level_values(0))

    for t in tickers:
        yf_t = _yf_symbol(t)
        if yf_t not in top_level:
            set_sync_error(conn, t, "price", "yfinance: ticker not in response")
            result[t] = "no_data"
            continue

        sub = df[yf_t]
        normalized = _normalize_yf_frame(t, sub)
        if normalized.empty:
            set_sync_error(conn, t, "price", "yfinance: empty frame")
            result[t] = "no_data"
            continue

        try:
            rows_inserted = _save_prices(conn, t, normalized)
            new_last = normalized["date"].max()
            set_sync_ok(conn, t, "price", new_last, rows_inserted)
            result[t] = "ok"
            log.info(f"[{t}] 写入 {rows_inserted} 条，最新={new_last}")
        except Exception as e:
            log.error(f"[{t}] 写库失败: {e}")
            set_sync_error(conn, t, "price", str(e))
            result[t] = f"error: {e}"

    return result


# 主循环：分批处理（全量回填）
log.info("=== Full rebase from 2010-01-01 ===")
for i in range(0, len(tickers), YF_BATCH_SIZE):
    batch = tickers[i:i+YF_BATCH_SIZE]
    log.info(f"=== Batch {i//YF_BATCH_SIZE + 1}/{(len(tickers)+YF_BATCH_SIZE-1)//YF_BATCH_SIZE} ===")
    update_prices_batch(batch, full_rebase=True)
    time.sleep(YF_BATCH_DELAY)

log.info("Done!")
conn.close()
```

- [ ] **Step 2: 验证语法**

Run: `python -m py_compile scripts/backfill_sp500_yfinance.py`
Expected: 无输出

- [ ] **Step 3: Commit**

```bash
git add scripts/backfill_sp500_yfinance.py
git commit -m "refactor: scripts/backfill_sp500_yfinance.py 使用 db.py/config.py"
```

---

### Task 10: 重构 scripts/backfill_hk_yfinance.py

**Files:**
- Modify: `scripts/backfill_hk_yfinance.py` - 使用 db.py/config.py

- [ ] **Step 1: 重写 scripts/backfill_hk_yfinance.py**

```python
#!/usr/bin/env python3
"""HK index backfill via yfinance - 使用 db.py 和 config.py"""

import yfinance as yf
import time
import pandas as pd
import logging
from datetime import date, timedelta

from db import get_conn, get_last_sync, set_sync_ok, set_sync_error
from config import DB, YF_RETRY_COUNT, YF_TIMEOUT, START_DATE_HK

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
log = logging.getLogger(__name__)

conn = get_conn()

# HK indices to backfill (db_ticker: yf_symbol)
INDEXES = {
    "HSI": "^HSI",
    "HSTECH": "3087.HK",
    "HSBI": "2800.HK",
}

log.info(f'HK indices: {list(INDEXES.keys())}')

HISTORY_YEARS = 15


def _save_prices(conn, ticker: str, df: pd.DataFrame) -> int:
    """INSERT IGNORE 写 prices 表"""
    sql = "INSERT IGNORE INTO prices (ticker, date, open, high, low, close, volume) VALUES (%s, %s, %s, %s, %s, %s, %s)"
    rows = [
        (ticker, r["date"],
         float(r["open"]) if pd.notna(r["open"]) else 0,
         float(r["high"]) if pd.notna(r["high"]) else 0,
         float(r["low"]) if pd.notna(r["low"]) else 0,
         float(r["close"]) if pd.notna(r["close"]) else 0,
         int(r["volume"]) if pd.notna(r["volume"]) else 0)
        for _, r in df.iterrows()
    ]
    with conn.cursor() as cur:
        cur.executemany(sql, rows)
    conn.commit()
    return len(rows)


def fetch_index(db_ticker: str, yf_symbol: str, full_rebase: bool = False) -> Dict:
    if full_rebase:
        start_dt = date.fromisoformat(START_DATE_HK)
    else:
        last = get_last_sync(conn, db_ticker, "price")
        if last:
            start_dt = last - timedelta(days=7)
        else:
            start_dt = date.today() - timedelta(days=365 * HISTORY_YEARS)

    end_dt = date.today() + timedelta(days=1)

    log.info(f"[{db_ticker}] {start_dt} → {end_dt}")

    for attempt in range(YF_RETRY_COUNT):
        try:
            t = yf.Ticker(yf_symbol)
            df = t.history(start=start_dt.isoformat(), end=end_dt.isoformat())
            break
        except Exception as e:
            if attempt < YF_RETRY_COUNT - 1:
                time.sleep(5 * (3 ** attempt))
                continue
            log.error(f"[{db_ticker}] failed: {e}")
            set_sync_error(conn, db_ticker, "price", str(e))
            return {"status": "error", "msg": str(e)}

    if df is None or df.empty:
        log.warning(f"[{db_ticker}] no data")
        set_sync_error(conn, db_ticker, "price", "no data")
        return {"status": "no_data"}

    df = df.reset_index()
    df["date"] = df["Date"].dt.date
    df = df.rename(columns={
        "Open": "open", "High": "high", "Low": "low",
        "Close": "close", "Volume": "volume"
    })
    df = df[["date", "open", "high", "low", "close", "volume"]].dropna(subset=["date", "close"])

    if df.empty:
        set_sync_error(conn, db_ticker, "price", "empty after clean")
        return {"status": "no_data"}

    rows = _save_prices(conn, db_ticker, df)
    new_last = df["date"].max()
    set_sync_ok(conn, db_ticker, "price", new_last, rows)
    log.info(f"[{db_ticker}] wrote {rows} rows, latest={new_last}")
    return {"status": "ok", "rows": rows}


log.info("=== Full rebase from 2010-01-01 ===")
for db_ticker, yf_symbol in INDEXES.items():
    fetch_index(db_ticker, yf_symbol, full_rebase=True)
    time.sleep(2)

log.info("Done!")
conn.close()
```

- [ ] **Step 2: 验证语法**

Run: `python -m py_compile scripts/backfill_hk_yfinance.py`
Expected: 无输出

- [ ] **Step 3: Commit**

```bash
git add scripts/backfill_hk_yfinance.py
git commit -m "refactor: scripts/backfill_hk_yfinance.py 使用 db.py/config.py"
```

---

### Task 11: 删除 scripts/clear_sp500_sync.py

**Files:**
- Delete: `scripts/clear_sp500_sync.py`

- [ ] **Step 1: 删除文件**

```bash
git rm scripts/clear_sp500_sync.py
```

- [ ] **Step 2: Commit**

```bash
git commit -m "chore: 删除硬编码密码脚本 clear_sp500_sync.py"
```

---

### Task 12: 运行测试验证重构

**Files:**
- Test: 全项目测试

- [ ] **Step 1: 运行现有测试**

Run: `pytest tests/ -v`
Expected: 所有测试通过

- [ ] **Step 2: 手动验证 init 命令**

Run: `python main.py init`
Expected: 正常输出

- [ ] **Step 3: 手动验证 status 命令**

Run: `python main.py status`
Expected: 正常输出

- [ ] **Step 4: 最终 Commit**

```bash
git add -A
git commit -m "refactor: 代码模块化重构完成

- 创建 data/index_base.py 提取共享helpers
- db.py 添加 get_latest_snapshot_tickers
- 重构 3个 index_updater 使用 index_base
- 重构 market_us/hk 使用 db.py
- 删除 stock_updater_us 死代码
- 重构 scripts 使用 db.py/config.py
- 删除硬编码密码脚本"
```