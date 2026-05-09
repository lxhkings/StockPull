# Unified Stocks Ingest (US + A股 + 港股) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `Project_B` as a unified daily-K data ingest service for three markets (US via yfinance, A-share via akshare/efinance, HK via akshare/efinance), writing into the existing shared MariaDB on Synology NAS.

**Architecture:** Port the proven Step 1/2/3 pipeline from `/Volumes/home/stock_system/` (snapshot constituents → backfill new → incremental). Generalize to dispatch per-market modules. Reuse the existing schema unchanged (`prices`, `stocks`, `indices`, `index_constituents`, `constituent_changes`, `index_prices`, `sync_log`, `index_sync_log`). A/HK store post-adjusted (hfq) close in `prices.close`; US stays raw (current behavior). hfq factor drift is handled by a `rebase` CLI command for full re-pull.

**Tech Stack:** Python 3.11+, pymysql, yfinance, akshare, efinance, pandas, requests, tenacity, python-dotenv, pytest.

---

## Reference: Existing Source Files

Throughout this plan, reads from `/Volumes/home/stock_system/` are needed:
- `config.py` — DB dict (hardcoded password, will be refactored)
- `db.py` — `get_conn`, `query`, `execute`, sync_log helpers
- `data/base.py` — HTTP retry, rate limiter, type converters
- `data/stock_updater.py` — yfinance batch fetcher
- `data/index_updater.py` — SP500 GitHub-CSV fetcher + change detection
- `data/pipeline.py` — Step 1/2/3 orchestration
- `main.py` — CLI entry
- `sql/schema_full.sql` — schema reference (DO NOT execute; tables already exist)

The MariaDB is at `192.168.8.9:3306`, database `stocks`, user `root`. Password goes into `.env` (NOT committed).

---

## Task 1: Project Scaffolding

**Files:**
- Create: `/Users/xiaohong/Project/Project_B/.gitignore`
- Create: `/Users/xiaohong/Project/Project_B/.env.example`
- Create: `/Users/xiaohong/Project/Project_B/pyproject.toml`
- Create: `/Users/xiaohong/Project/Project_B/requirements.txt`
- Create: `/Users/xiaohong/Project/Project_B/README.md`
- Create: `/Users/xiaohong/Project/Project_B/data/__init__.py`
- Create: `/Users/xiaohong/Project/Project_B/tests/__init__.py`

- [ ] **Step 1: Init git and create dirs**

```bash
cd /Users/xiaohong/Project/Project_B
git init
mkdir -p data tests scripts sql logs docs/superpowers/plans
touch data/__init__.py tests/__init__.py
```

- [ ] **Step 2: Write `.gitignore`**

```
# Project_B/.gitignore
.env
logs/
__pycache__/
*.pyc
*.pyo
.venv/
venv/
.pytest_cache/
.mypy_cache/
.DS_Store
*.egg-info/
dist/
build/
cache/
```

- [ ] **Step 3: Write `.env.example`**

```
DB_HOST=192.168.8.9
DB_PORT=3306
DB_USER=root
DB_PASSWORD=
DB_NAME=stocks
```

- [ ] **Step 4: Write `requirements.txt`**

```
pymysql>=1.0.3
yfinance>=0.2.40
akshare>=1.16.0
efinance>=0.5.4
pandas>=1.5.0
numpy>=1.23.0
requests>=2.28.0
python-dateutil>=2.8.2
python-dotenv>=1.0.0
tenacity>=8.2.0
pytest>=7.4.0
```

- [ ] **Step 5: Write `pyproject.toml`** (minimal — pytest config + tool defaults)

```toml
[build-system]
requires = ["setuptools>=68.0"]
build-backend = "setuptools.build_meta"

[project]
name = "project-b"
version = "0.1.0"
description = "Unified daily-K ingest (US + A-share + HK) writing into shared NAS MariaDB"
requires-python = ">=3.11"

[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]
addopts = "-v"
```

- [ ] **Step 6: Write `README.md`** (skeleton; full content in Task 22)

```markdown
# Project_B — Unified Stocks Ingest

Daily-K ingest for US (yfinance) + A-share (akshare/efinance) + HK (akshare/efinance), writing into shared NAS MariaDB.

See `docs/superpowers/plans/` for the implementation plan.

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # fill DB_PASSWORD
python main.py init      # one-time: insert CSI800/HSI rows into indices table
python main.py daily     # run all markets
```
```

- [ ] **Step 7: Commit**

```bash
git add .gitignore .env.example pyproject.toml requirements.txt README.md data/__init__.py tests/__init__.py
git commit -m "scaffold: Project_B layout and tooling"
```

---

## Task 2: Set up venv and install dependencies

**Files:** None (environment setup)

- [ ] **Step 1: Create venv and install**

```bash
cd /Users/xiaohong/Project/Project_B
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

- [ ] **Step 2: Verify imports**

```bash
python -c "import pymysql, yfinance, akshare, efinance, pandas, dotenv, tenacity; print('OK')"
```

Expected output: `OK`

- [ ] **Step 3: Note**

The venv is gitignored. Each developer creates their own.

No commit needed — environment-only.

---

## Task 3: `config.py` with dotenv

**Files:**
- Create: `/Users/xiaohong/Project/Project_B/config.py`
- Create: `/Users/xiaohong/Project/Project_B/.env` (LOCAL ONLY; not committed)
- Create: `/Users/xiaohong/Project/Project_B/tests/test_config.py`

- [ ] **Step 1: Create local `.env`** (not committed)

```bash
cat > /Users/xiaohong/Project/Project_B/.env <<'EOF'
DB_HOST=192.168.8.9
DB_PORT=3306
DB_USER=root
DB_PASSWORD=18620001807@Aa
DB_NAME=stocks
EOF
chmod 600 .env
```

- [ ] **Step 2: Write the failing test** at `tests/test_config.py`

```python
import os
from unittest.mock import patch

def test_db_dict_is_assembled_from_env():
    """config.DB reads from environment via dotenv."""
    from config import DB
    assert DB["host"] == os.environ["DB_HOST"]
    assert DB["port"] == int(os.environ["DB_PORT"])
    assert DB["user"] == os.environ["DB_USER"]
    assert DB["password"] == os.environ["DB_PASSWORD"]
    assert DB["database"] == os.environ["DB_NAME"]
    assert DB["charset"] == "utf8mb4"
    assert DB["autocommit"] is False


def test_history_years_defaults_per_market():
    from config import HISTORY_YEARS_US, HISTORY_YEARS_CN, HISTORY_YEARS_HK, START_DATE_CN
    assert HISTORY_YEARS_US == 5
    assert HISTORY_YEARS_CN == 15
    assert HISTORY_YEARS_HK == 15
    assert START_DATE_CN == "2010-01-01"


def test_indices_metadata():
    from config import INDEX_CONFIG
    assert "SP500" in INDEX_CONFIG
    assert "CSI800" in INDEX_CONFIG
    assert "HSI" in INDEX_CONFIG
    assert INDEX_CONFIG["CSI800"]["etf"] == "510800"
    assert INDEX_CONFIG["HSI"]["etf"] == "2800.HK"
```

- [ ] **Step 3: Run test — expect failure**

```bash
source .venv/bin/activate
pytest tests/test_config.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'config'`.

- [ ] **Step 4: Implement `config.py`**

```python
"""Global configuration. Reads secrets from .env (python-dotenv).

Per-market history depths and ingest defaults live here.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# Database — reads from .env, no fallback for password
DB = {
    "host":       os.getenv("DB_HOST", "192.168.8.9"),
    "port":       int(os.getenv("DB_PORT", "3306")),
    "user":       os.getenv("DB_USER", "root"),
    "password":   os.environ["DB_PASSWORD"],   # required, raises KeyError if missing
    "database":   os.getenv("DB_NAME", "stocks"),
    "charset":    "utf8mb4",
    "autocommit": False,
}

# History depths per market
HISTORY_YEARS_US = 5
HISTORY_YEARS_CN = 15
HISTORY_YEARS_HK = 15
START_DATE_CN    = "2010-01-01"
START_DATE_HK    = "2010-01-01"

# yfinance (carried over from stock_system)
YF_BATCH_SIZE    = 20
YF_RETRY_COUNT   = 3
YF_TIMEOUT       = 30
YF_LOOKBACK_DAYS = 7
YF_THREADS       = False
YF_BATCH_DELAY   = 2.0

# A-share / HK source delays (akshare is sometimes flaky; serial)
AKSHARE_RETRY_COUNT = 3
AKSHARE_RETRY_DELAY = 2.0
AKSHARE_REQUEST_DELAY = 0.5  # between per-stock calls

# Reconcile tolerance for two-source comparison
RECONCILE_PRICE_TOLERANCE = 0.005   # 0.5%

# Index metadata. etf required by indices.etf_ticker NOT NULL.
INDEX_CONFIG = {
    "SP500": {
        "name":   "S&P 500",
        "source": "github",
        "etf":    "IVV",
        "market": "us",
        "description": "iShares Core S&P 500 ETF",
    },
    "CSI800": {
        "name":   "中证800",
        "source": "akshare",
        "etf":    "510800",
        "market": "cn",
        "description": "中证800ETF (华夏)",
        "ak_symbol": "000906",
    },
    "HSI": {
        "name":   "恒生指数",
        "source": "akshare",
        "etf":    "2800.HK",
        "market": "hk",
        "description": "盈富基金 Tracker Fund",
        "ak_symbol": "HSI",
    },
}

INDEX_DELAY = 2.0   # delay between index updates (carried over)
```

- [ ] **Step 5: Run tests — expect pass**

```bash
pytest tests/test_config.py -v
```

Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add config.py tests/test_config.py
git commit -m "config: dotenv-driven config with per-market settings"
```

---

## Task 4: Port `db.py` (with timezone fix)

**Files:**
- Create: `/Users/xiaohong/Project/Project_B/db.py`
- Create: `/Users/xiaohong/Project/Project_B/tests/test_db_smoke.py`

- [ ] **Step 1: Copy existing db.py with one modification**

Copy the full content of `/Volumes/home/stock_system/db.py` to `/Users/xiaohong/Project/Project_B/db.py`. Then modify `get_conn()` to set the time zone:

```python
def get_conn() -> pymysql.Connection:
    """获取数据库连接（设置 +08:00 时区，避免 created_at 偏 8 小时）"""
    conn = pymysql.connect(**DB)
    with conn.cursor() as cur:
        cur.execute("SET time_zone = '+08:00'")
    return conn
```

Keep `query`, `execute`, `get_last_sync`, `set_sync_ok`, `set_sync_error`, `_upsert_sync_log`, `get_all_stocks`, `get_index_tickers`, `get_tickers_without_prices`, `show_status` exactly as-is.

- [ ] **Step 2: Write smoke test** at `tests/test_db_smoke.py`

```python
"""Live DB smoke test. Skip with `pytest -m 'not smoke'` if NAS unreachable."""

import pytest
import socket
from datetime import date


def _nas_reachable():
    try:
        with socket.create_connection(("192.168.8.9", 3306), timeout=2):
            return True
    except OSError:
        return False


pytestmark = pytest.mark.skipif(not _nas_reachable(), reason="NAS DB not reachable")


def test_get_conn_succeeds():
    from db import get_conn
    conn = get_conn()
    try:
        assert conn.open
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            assert cur.fetchone() == (1,)
    finally:
        conn.close()


def test_existing_schema_tables_present():
    """Confirm we are talking to the right DB (the one stock_system uses)."""
    from db import query
    rows = query("SHOW TABLES")
    table_names = {next(iter(r.values())) for r in rows}
    expected = {"stocks", "prices", "indices", "index_constituents",
                "constituent_changes", "index_prices", "sync_log", "index_sync_log"}
    assert expected.issubset(table_names), f"Missing tables: {expected - table_names}"


def test_sync_log_roundtrip():
    """Write/read a probe row in sync_log."""
    from db import get_conn, set_sync_ok, get_last_sync
    conn = get_conn()
    try:
        probe_ticker = "__PROBE__"
        set_sync_ok(conn, probe_ticker, "price", date(2026, 5, 9), 0)
        last = get_last_sync(conn, probe_ticker, "price")
        assert last == date(2026, 5, 9)
        # Cleanup
        with conn.cursor() as cur:
            cur.execute("DELETE FROM sync_log WHERE ticker=%s", (probe_ticker,))
        conn.commit()
    finally:
        conn.close()
```

- [ ] **Step 3: Run smoke test**

```bash
pytest tests/test_db_smoke.py -v
```

Expected: 3 passed (or all skipped if NAS unreachable).

- [ ] **Step 4: Commit**

```bash
git add db.py tests/test_db_smoke.py
git commit -m "db: port db.py with +08:00 time_zone fix"
```

---

## Task 5: Port `data/base.py` (no changes)

**Files:**
- Create: `/Users/xiaohong/Project/Project_B/data/base.py`

- [ ] **Step 1: Copy file verbatim**

```bash
cp /Volumes/home/stock_system/data/base.py /Users/xiaohong/Project/Project_B/data/base.py
```

- [ ] **Step 2: Verify import**

```bash
cd /Users/xiaohong/Project/Project_B && source .venv/bin/activate
python -c "from data.base import to_float, to_int, format_cik, fetch_with_retry, RateLimiter; print('OK')"
```

Expected: `OK`.

- [ ] **Step 3: Commit**

```bash
git add data/base.py
git commit -m "data: port base.py (HTTP retry / rate limiter / type converters)"
```

---

## Task 6: `data/ticker_utils.py` (TDD)

**Files:**
- Create: `/Users/xiaohong/Project/Project_B/data/ticker_utils.py`
- Create: `/Users/xiaohong/Project/Project_B/tests/test_ticker_utils.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_ticker_utils.py
import pytest

from data.ticker_utils import (
    parse_ticker,
    to_akshare_a,
    to_akshare_hk,
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


def test_to_akshare_a_strips_suffix():
    assert to_akshare_a("600519.SH") == "600519"
    assert to_akshare_a("000001.SZ") == "000001"


def test_to_akshare_a_rejects_non_a():
    with pytest.raises(ValueError):
        to_akshare_a("AAPL")
    with pytest.raises(ValueError):
        to_akshare_a("00700.HK")


def test_to_akshare_hk_strips_and_pads():
    assert to_akshare_hk("00700.HK") == "00700"
    assert to_akshare_hk("09988.HK") == "09988"


def test_to_akshare_hk_rejects_non_hk():
    with pytest.raises(ValueError):
        to_akshare_hk("600519.SH")


def test_to_yfinance_us_dot_to_dash():
    """yfinance: BRK.B → BRK-B."""
    assert to_yfinance_us("AAPL") == "AAPL"
    assert to_yfinance_us("BRK.B") == "BRK-B"
```

- [ ] **Step 2: Run — expect fail**

```bash
pytest tests/test_ticker_utils.py -v
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement `data/ticker_utils.py`**

```python
"""Ticker format conversion across markets and source APIs.

Internal canonical formats:
  US: bare uppercase, e.g., AAPL, BRK.B, BRK-B
  A-share SH: <6-digit>.SH, e.g., 600519.SH, 688981.SH
  A-share SZ: <6-digit>.SZ, e.g., 000001.SZ, 300750.SZ
  HK: <5-digit>.HK, e.g., 00700.HK, 09988.HK
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class Market(str, Enum):
    US = "us"
    CN = "cn"
    HK = "hk"


@dataclass(frozen=True)
class ParsedTicker:
    code: str
    suffix: Optional[str]   # 'SH' / 'SZ' / 'HK' / None (US)


_SUFFIX_RE = re.compile(r"^(?P<code>[A-Z0-9.\-]+)\.(?P<suffix>SH|SZ|HK)$")


def parse_ticker(ticker: str) -> ParsedTicker:
    t = ticker.strip().upper()
    m = _SUFFIX_RE.match(t)
    if m:
        return ParsedTicker(code=m.group("code"), suffix=m.group("suffix"))
    return ParsedTicker(code=t, suffix=None)


def infer_market(ticker: str) -> Market:
    p = parse_ticker(ticker)
    if p.suffix in ("SH", "SZ"):
        return Market.CN
    if p.suffix == "HK":
        return Market.HK
    return Market.US


def infer_a_exchange(code: str) -> str:
    """A-share code → SH or SZ (per Shanghai/Shenzhen prefix rules)."""
    if code.startswith(("6", "9")) or code.startswith("68"):
        return "SH"
    if code.startswith(("0", "3", "2")):
        return "SZ"
    raise ValueError(f"Unknown A-share prefix: {code}")


def to_akshare_a(ticker: str) -> str:
    """A-share canonical → akshare 6-digit code."""
    p = parse_ticker(ticker)
    if p.suffix not in ("SH", "SZ"):
        raise ValueError(f"Not an A-share ticker: {ticker}")
    return p.code


def to_akshare_hk(ticker: str) -> str:
    """HK canonical → akshare 5-digit code (preserve leading zeros)."""
    p = parse_ticker(ticker)
    if p.suffix != "HK":
        raise ValueError(f"Not a HK ticker: {ticker}")
    return p.code.zfill(5)


def to_efinance_a(ticker: str) -> str:
    """efinance A-share: same 6-digit code."""
    return to_akshare_a(ticker)


def to_efinance_hk(ticker: str) -> str:
    """efinance HK: 5-digit code."""
    return to_akshare_hk(ticker)


def to_yfinance_us(ticker: str) -> str:
    """yfinance: dot → dash (BRK.B → BRK-B)."""
    return ticker.upper().replace(".", "-")


def from_akshare_a(code: str) -> str:
    """akshare 6-digit code → canonical with .SH/.SZ suffix."""
    code = code.strip()
    return f"{code}.{infer_a_exchange(code)}"


def from_akshare_hk(code: str) -> str:
    """akshare HK 5-digit → canonical .HK suffix."""
    return f"{code.strip().zfill(5)}.HK"
```

- [ ] **Step 4: Run — expect pass**

```bash
pytest tests/test_ticker_utils.py -v
```

Expected: all parametrized cases pass.

- [ ] **Step 5: Commit**

```bash
git add data/ticker_utils.py tests/test_ticker_utils.py
git commit -m "data: ticker_utils for cross-market format conversion"
```

---

## Task 7: Port `data/stock_updater_us.py`

**Files:**
- Create: `/Users/xiaohong/Project/Project_B/data/stock_updater_us.py`

- [ ] **Step 1: Copy and rename**

```bash
cp /Volumes/home/stock_system/data/stock_updater.py \
   /Users/xiaohong/Project/Project_B/data/stock_updater_us.py
```

- [ ] **Step 2: Adapt imports** in `data/stock_updater_us.py`

The existing file imports:
```python
from config import HISTORY_YEARS, YF_BATCH_SIZE, YF_RETRY_COUNT, YF_TIMEOUT, YF_LOOKBACK_DAYS, YF_THREADS
```

Change to:
```python
from config import (
    HISTORY_YEARS_US as HISTORY_YEARS,
    YF_BATCH_SIZE, YF_RETRY_COUNT, YF_TIMEOUT,
    YF_LOOKBACK_DAYS, YF_THREADS,
)
```

Keep all other code (functions `update_prices`, `update_prices_batch`, `_yf_symbol`, `_normalize_yf_frame`, `_save_prices`, `guess_yf_ticker`) unchanged.

- [ ] **Step 3: Verify import**

```bash
python -c "from data.stock_updater_us import update_prices_batch, update_prices; print('OK')"
```

Expected: `OK`.

- [ ] **Step 4: Smoke test against live API** (1 ticker)

```bash
python -c "
from data.stock_updater_us import update_prices_batch
result = update_prices_batch(['AAPL'])
print(result)
"
```

Expected: `{'AAPL': 'ok'}` or similar; check `prices` table in DB has new rows.

- [ ] **Step 5: Commit**

```bash
git add data/stock_updater_us.py
git commit -m "data: port stock_updater_us (yfinance batch fetcher)"
```

---

## Task 8: Port `data/index_updater_us.py`

**Files:**
- Create: `/Users/xiaohong/Project/Project_B/data/index_updater_us.py`

- [ ] **Step 1: Copy and rename**

```bash
cp /Volumes/home/stock_system/data/index_updater.py \
   /Users/xiaohong/Project/Project_B/data/index_updater_us.py
```

- [ ] **Step 2: Adapt imports**

The file imports `from config import INDEX_DELAY` and `from db import get_conn` and `from data.base import fetch_urls_sequentially, format_cik`. These all work as-is in Project_B.

The file imports `from datetime import date` — also fine.

No changes needed beyond the rename. Verify by reading the file with `head -30`.

- [ ] **Step 3: Verify import**

```bash
python -c "from data.index_updater_us import update_sp500; print('OK')"
```

Expected: `OK`.

- [ ] **Step 4: Smoke test** (live)

```bash
python -c "
from data.index_updater_us import update_sp500
update_sp500()
"
```

Expected: log line `[SP500] 完成 ...`. If today's snapshot already exists, log says "今日已更新，跳过" — that's also a pass.

- [ ] **Step 5: Commit**

```bash
git add data/index_updater_us.py
git commit -m "data: port index_updater_us (SP500 GitHub CSV)"
```

---

## Task 9: Refactor `data/pipeline.py` for per-market dispatch

**Files:**
- Create: `/Users/xiaohong/Project/Project_B/data/pipeline.py`
- Create: `/Users/xiaohong/Project/Project_B/tests/test_pipeline.py`

- [ ] **Step 1: Read original** at `/Volumes/home/stock_system/data/pipeline.py` to understand the Step 1/2/3 pattern. The new `pipeline.py` defines a generic `Pipeline` orchestrator that takes a market module exposing four callables.

- [ ] **Step 2: Write failing test** `tests/test_pipeline.py`

```python
from unittest.mock import MagicMock, call


def test_pipeline_runs_steps_in_order():
    """Pipeline calls update_index → backfill_new → incremental → update_index_price."""
    from data.pipeline import Pipeline

    market_module = MagicMock()
    market_module.market_id = "us"
    market_module.update_index.return_value = (["NEW1", "NEW2"], 5, 1)  # (new_added_tickers, total_inserted, removed)
    market_module.list_active_tickers.return_value = ["AAPL", "MSFT", "NEW1", "NEW2"]
    market_module.backfill_new.return_value = {"NEW1": "ok", "NEW2": "ok"}
    market_module.incremental.return_value = {"AAPL": "ok", "MSFT": "ok", "NEW1": "ok", "NEW2": "ok"}
    market_module.update_index_price.return_value = 1

    p = Pipeline(market_module)
    p.daily()

    market_module.update_index.assert_called_once()
    market_module.backfill_new.assert_called_once_with(["NEW1", "NEW2"])
    market_module.incremental.assert_called_once_with(["AAPL", "MSFT", "NEW1", "NEW2"])
    market_module.update_index_price.assert_called_once()


def test_pipeline_skips_backfill_when_no_new():
    from data.pipeline import Pipeline

    market_module = MagicMock()
    market_module.market_id = "cn"
    market_module.update_index.return_value = ([], 0, 0)
    market_module.list_active_tickers.return_value = ["600519.SH"]
    market_module.incremental.return_value = {"600519.SH": "ok"}
    market_module.update_index_price.return_value = 1

    Pipeline(market_module).daily()

    market_module.backfill_new.assert_not_called()
    market_module.incremental.assert_called_once()
```

- [ ] **Step 3: Run — expect fail**

```bash
pytest tests/test_pipeline.py -v
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 4: Implement `data/pipeline.py`**

```python
"""Generic per-market pipeline orchestrator.

A market module must expose:
  market_id: str
  update_index() -> tuple[list[str], int, int]
      (new_tickers_added_today, total_inserted, removed_count)
  list_active_tickers() -> list[str]
      All tickers currently in this market's universe.
  backfill_new(new_tickers: list[str]) -> dict[str, str]
      Pull full history for newly added tickers. Returns per-ticker status.
  incremental(tickers: list[str]) -> dict[str, str]
      Resume-from-sync_log for existing tickers.
  update_index_price() -> int
      Update the index's own daily close. Returns rows inserted.
  rebase(tickers: list[str] | None = None) -> dict[str, str]
      Full re-pull from START_DATE for hfq rebase. Optional to implement
      (US module raises NotImplementedError).
"""

from __future__ import annotations

import logging
from typing import Protocol

log = logging.getLogger(__name__)


class MarketModule(Protocol):
    market_id: str
    def update_index(self) -> tuple[list[str], int, int]: ...
    def list_active_tickers(self) -> list[str]: ...
    def backfill_new(self, new_tickers: list[str]) -> dict[str, str]: ...
    def incremental(self, tickers: list[str]) -> dict[str, str]: ...
    def update_index_price(self) -> int: ...


class Pipeline:
    def __init__(self, market_module: MarketModule):
        self.m = market_module

    def daily(self) -> None:
        mid = self.m.market_id
        log.info(f"[{mid}] === Step 1: update index constituents ===")
        new_tickers, inserted, removed = self.m.update_index()
        log.info(f"[{mid}] index: +{len(new_tickers)} new, {inserted} rows in snapshot, -{removed} removed")

        if new_tickers:
            log.info(f"[{mid}] === Step 2: backfill {len(new_tickers)} new tickers ===")
            self.m.backfill_new(new_tickers)

        log.info(f"[{mid}] === Step 3: incremental update ===")
        all_tickers = self.m.list_active_tickers()
        self.m.incremental(all_tickers)

        log.info(f"[{mid}] === Step 4: update index price ===")
        rows = self.m.update_index_price()
        log.info(f"[{mid}] index price: +{rows} rows")
        log.info(f"[{mid}] === pipeline complete ===")
```

- [ ] **Step 5: Run — expect pass**

```bash
pytest tests/test_pipeline.py -v
```

Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add data/pipeline.py tests/test_pipeline.py
git commit -m "pipeline: generic per-market orchestrator (Step 1/2/3/4)"
```

---

## Task 10: Build US market module wrapper

**Files:**
- Create: `/Users/xiaohong/Project/Project_B/data/market_us.py`

- [ ] **Step 1: Implement** `data/market_us.py`

```python
"""US market module: thin adapter exposing the MarketModule protocol.

Wraps existing index_updater_us.update_sp500() and stock_updater_us.update_prices_batch()
into the Pipeline contract.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Optional

import yfinance as yf

from db import get_conn, get_index_tickers, query, execute
from data import index_updater_us
from data import stock_updater_us
from data.base import to_float

log = logging.getLogger(__name__)

market_id = "us"


def update_index() -> tuple[list[str], int, int]:
    """Run SP500 snapshot + change detection. Returns (new_added_tickers, inserted, removed)."""
    conn = get_conn()
    try:
        prev_tickers = set(_latest_snapshot_tickers(conn, "SP500"))
    finally:
        conn.close()

    index_updater_us.update_sp500()

    conn = get_conn()
    try:
        curr_tickers = set(_latest_snapshot_tickers(conn, "SP500"))
    finally:
        conn.close()

    new_added = sorted(curr_tickers - prev_tickers)
    removed = len(prev_tickers - curr_tickers)
    return new_added, len(curr_tickers), removed


def list_active_tickers() -> list[str]:
    return get_index_tickers("SP500")


def backfill_new(new_tickers: list[str]) -> dict[str, str]:
    """Backfill = full HISTORY_YEARS_US pull. Same code path as incremental
    because sync_log will be empty for these tickers."""
    if not new_tickers:
        return {}
    return stock_updater_us.update_prices_batch(new_tickers)


def incremental(tickers: list[str]) -> dict[str, str]:
    if not tickers:
        return {}
    return stock_updater_us.update_prices_batch(tickers)


def update_index_price() -> int:
    """Pull ^GSPC daily close from yfinance, write to index_prices."""
    last = query(
        "SELECT MAX(date) AS d FROM index_prices WHERE index_id=%s", ("SP500",)
    )
    last_date = last[0]["d"] if last and last[0]["d"] else None

    start = last_date.isoformat() if last_date else "2010-01-01"
    df = yf.download("^GSPC", start=start, interval="1d",
                     auto_adjust=False, actions=False, progress=False)
    if df.empty:
        return 0

    df = df.reset_index()
    df.columns = [str(c).lower() if not isinstance(c, tuple) else str(c[0]).lower() for c in df.columns]
    rows = []
    for _, r in df.iterrows():
        d = r["date"].date() if hasattr(r["date"], "date") else r["date"]
        if last_date and d <= last_date:
            continue
        rows.append((d, "SP500", to_float(r.get("close"))))

    if not rows:
        return 0

    return execute(
        "INSERT IGNORE INTO index_prices (date, index_id, close) VALUES (%s,%s,%s)",
        rows, many=True
    )


def rebase(tickers: Optional[list[str]] = None) -> dict[str, str]:
    """US rebase is identical to incremental from the user's perspective:
    yfinance auto_adjust=False stores raw, and prior US data does not need hfq rebase."""
    raise NotImplementedError("US rebase not supported (raw prices, no hfq drift). "
                              "Use `daily` to refresh recent data.")


def _latest_snapshot_tickers(conn, index_id: str) -> list[str]:
    rows = query(
        """SELECT DISTINCT ticker FROM index_constituents
           WHERE index_id=%s AND snapshot_date = (
             SELECT MAX(snapshot_date) FROM index_constituents WHERE index_id=%s
           )""",
        (index_id, index_id)
    )
    return [r["ticker"] for r in rows]
```

- [ ] **Step 2: Smoke test**

```bash
python -c "
from data.pipeline import Pipeline
from data import market_us
Pipeline(market_us).daily()
"
```

Expected: pipeline runs all 4 steps; check DB tables `prices`, `index_prices`, `index_constituents` for fresh rows.

- [ ] **Step 3: Commit**

```bash
git add data/market_us.py
git commit -m "data: market_us module adapting US ingest to Pipeline protocol"
```

---

## Task 11: `main.py` CLI skeleton

**Files:**
- Create: `/Users/xiaohong/Project/Project_B/main.py`
- Create: `/Users/xiaohong/Project/Project_B/tests/test_cli.py`

- [ ] **Step 1: Write failing test** `tests/test_cli.py`

```python
import subprocess
import sys


def _run(*args):
    return subprocess.run(
        [sys.executable, "main.py", *args],
        capture_output=True, text=True
    )


def test_help_shows_subcommands():
    out = _run("--help")
    assert out.returncode == 0
    for sub in ("init", "daily", "rebase", "status"):
        assert sub in out.stdout


def test_unknown_subcommand_errors():
    out = _run("nonexistent")
    assert out.returncode != 0


def test_daily_market_choice_validated():
    out = _run("daily", "--market", "europe")
    assert out.returncode != 0
    assert "europe" in out.stderr or "europe" in out.stdout
```

- [ ] **Step 2: Run — expect fail**

```bash
pytest tests/test_cli.py -v
```

Expected: `main.py` not found.

- [ ] **Step 3: Implement `main.py`**

```python
"""Project_B CLI entry. Subcommands: init / daily / rebase / status."""

from __future__ import annotations

import argparse
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

MARKETS = ("us", "cn", "hk", "all")


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="main.py", description="Unified ingest for US/CN/HK")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="Insert CSI800/HSI rows into indices table (idempotent)")

    p_daily = sub.add_parser("daily", help="Run incremental daily ingest")
    p_daily.add_argument("--market", choices=MARKETS, default="all")
    p_daily.add_argument("--code", action="append", default=None,
                         help="Only this ticker (repeatable, debug aid)")

    p_rebase = sub.add_parser("rebase", help="Full re-pull (hfq drift fix)")
    p_rebase.add_argument("--market", choices=("cn", "hk"), required=True)
    p_rebase.add_argument("--code", action="append", default=None)

    sub.add_parser("status", help="Print ingest status summary")

    return p


def cmd_init() -> int:
    from db import execute
    from config import INDEX_CONFIG
    rows = [
        (idx, cfg["name"], cfg["etf"], cfg["description"])
        for idx, cfg in INDEX_CONFIG.items()
    ]
    n = execute(
        "INSERT IGNORE INTO indices (index_id, name, etf_ticker, description) "
        "VALUES (%s,%s,%s,%s)",
        rows, many=True,
    )
    print(f"init: inserted {n} new rows into `indices` (existing rows unchanged)")
    return 0


def cmd_status() -> int:
    from db import show_status
    show_status()
    return 0


def cmd_daily(market: str, codes: list[str] | None) -> int:
    from data.pipeline import Pipeline
    targets = ["us", "cn", "hk"] if market == "all" else [market]
    for m in targets:
        try:
            mod = _import_market(m)
        except ImportError as e:
            print(f"[{m}] not yet implemented: {e}", file=sys.stderr)
            continue

        if codes:
            # Single-ticker debug path: skip Step 1/2, run incremental on the codes only
            print(f"[{m}] daily --code {codes}: running incremental only")
            mod.incremental(codes)
        else:
            Pipeline(mod).daily()
    return 0


def cmd_rebase(market: str, codes: list[str] | None) -> int:
    mod = _import_market(market)
    if not hasattr(mod, "rebase"):
        print(f"[{market}] rebase not implemented", file=sys.stderr)
        return 1
    targets = codes or mod.list_active_tickers()
    print(f"[{market}] rebase {len(targets)} tickers (full history)")
    mod.rebase(targets)
    return 0


def _import_market(market: str):
    if market == "us":
        from data import market_us as m
    elif market == "cn":
        from data import market_cn as m
    elif market == "hk":
        from data import market_hk as m
    else:
        raise ValueError(market)
    return m


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.cmd == "init":
        return cmd_init()
    if args.cmd == "status":
        return cmd_status()
    if args.cmd == "daily":
        return cmd_daily(args.market, args.code)
    if args.cmd == "rebase":
        return cmd_rebase(args.market, args.code)
    return 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run — expect pass**

```bash
pytest tests/test_cli.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Smoke test `init`**

```bash
python main.py init
```

Expected: `init: inserted N new rows ...`. Verify in DB:
```sql
SELECT * FROM indices;
-- Should now show SP500, CSI800, HSI rows.
```

- [ ] **Step 6: Smoke test `status`**

```bash
python main.py status
```

Expected: stocks total / prices count / errors lines printed.

- [ ] **Step 7: Smoke test `daily --market us`** (idempotent — re-running today is fine)

```bash
python main.py daily --market us
```

Expected: pipeline logs all 4 steps. If SP500 already snapshotted today: "今日已更新，跳过" + still runs Step 3.

- [ ] **Step 8: Commit**

```bash
git add main.py tests/test_cli.py
git commit -m "cli: main.py with init/daily/rebase/status subcommands"
```

---

## Task 12: `data/index_updater_cn.py` (CSI800)

**Files:**
- Create: `/Users/xiaohong/Project/Project_B/data/index_updater_cn.py`
- Create: `/Users/xiaohong/Project/Project_B/tests/test_index_updater_cn.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_index_updater_cn.py
from unittest.mock import patch, MagicMock
import pandas as pd
from datetime import date


def _ak_csi800_df():
    return pd.DataFrame({
        "成分券代码": ["600519", "000001", "300750"],
        "成分券名称": ["贵州茅台", "平安银行", "宁德时代"],
        "行业": ["食品饮料", "银行", "电力设备"],
    })


@patch("data.index_updater_cn.ak.index_stock_cons_csindex")
def test_fetch_csi800_normalizes_to_canonical_tickers(mock_ak):
    from data.index_updater_cn import _fetch_csi800
    mock_ak.return_value = _ak_csi800_df()
    df = _fetch_csi800()
    assert set(df["ticker"]) == {"600519.SH", "000001.SZ", "300750.SZ"}
    assert "name" in df.columns
    assert "sector" in df.columns


@patch("data.index_updater_cn._fetch_csi800")
@patch("data.index_updater_cn.get_conn")
def test_update_csi800_skips_when_today_already_done(mock_conn, mock_fetch):
    """If snapshot already exists for today, skip without calling akshare."""
    from data.index_updater_cn import update_csi800
    cur = MagicMock()
    cur.fetchone.return_value = (date.today(),)
    mock_conn.return_value.cursor.return_value.__enter__.return_value = cur
    update_csi800()
    mock_fetch.assert_not_called()
```

- [ ] **Step 2: Run — expect fail**

```bash
pytest tests/test_index_updater_cn.py -v
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement `data/index_updater_cn.py`**

```python
"""CSI800 (中证800) constituent updater via akshare.

Mirrors stock_system/data/index_updater.py:update_sp500() flow:
  1. fetch current constituents
  2. write index_constituents snapshot
  3. detect ADDED/REMOVED vs prev snapshot
  4. upsert stocks rows
  5. write index_sync_log
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Optional, Set, Tuple

import akshare as ak
import pandas as pd

from db import get_conn
from data.ticker_utils import from_akshare_a

log = logging.getLogger(__name__)

INDEX_ID = "CSI800"
AK_SYMBOL = "000906"


def update_csi800() -> None:
    conn = get_conn()
    try:
        prev_date = _get_last_snapshot_date(conn, INDEX_ID)
        if prev_date == date.today():
            log.info(f"[{INDEX_ID}] 今日已更新，跳过")
            return

        df = _fetch_csi800()
        if df is None or df.empty:
            log.error(f"[{INDEX_ID}] 获取数据失败")
            _upsert_index_log(conn, INDEX_ID, date.today(), 0, 0, 0, "error", "无数据")
            return

        snap = date.today()
        new_set = set(df["ticker"].unique())
        inserted = _save_snapshot(conn, df, INDEX_ID, snap)
        added, removed = _detect_changes(conn, INDEX_ID, snap, new_set, prev_date)
        _register_stocks(conn, df)
        _upsert_index_log(conn, INDEX_ID, snap, inserted, added, removed)
        log.info(f"[{INDEX_ID}] 完成 {snap}: {inserted}条 +{added} -{removed}")
    except Exception as e:
        log.error(f"[{INDEX_ID}] 更新失败: {e}")
        _upsert_index_log(conn, INDEX_ID, date.today(), 0, 0, 0, "error", str(e))
    finally:
        conn.close()


def _fetch_csi800() -> pd.DataFrame:
    raw = ak.index_stock_cons_csindex(symbol=AK_SYMBOL)
    # akshare returns columns: 成分券代码, 成分券名称, 行业, ...
    df = pd.DataFrame({
        "ticker": [from_akshare_a(c) for c in raw["成分券代码"].astype(str).str.zfill(6)],
        "name":   raw["成分券名称"],
        "sector": raw.get("行业", ""),
    })
    return df


def _get_last_snapshot_date(conn, index_id: str) -> Optional[date]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT MAX(snapshot_date) FROM index_constituents WHERE index_id=%s",
            (index_id,)
        )
        row = cur.fetchone()
    return row[0] if row and row[0] else None


def _save_snapshot(conn, df: pd.DataFrame, index_id: str, snap: date) -> int:
    rows = [
        (index_id, snap, r["ticker"], r["name"], r["sector"])
        for _, r in df.iterrows()
    ]
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT IGNORE INTO index_constituents "
            "(index_id, snapshot_date, ticker, name, sector) VALUES (%s,%s,%s,%s,%s)",
            rows
        )
    conn.commit()
    return len(rows)


def _detect_changes(conn, index_id: str, snap: date,
                    new_set: Set[str], prev_date: Optional[date]) -> Tuple[int, int]:
    if prev_date is None:
        # First-ever snapshot: write all as ADDED
        rows = [(index_id, t, "", "ADDED", snap, None) for t in new_set]
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT IGNORE INTO constituent_changes "
                "(index_id, ticker, name, change_type, change_date, prev_date) "
                "VALUES (%s,%s,%s,%s,%s,%s)",
                rows
            )
        conn.commit()
        return len(rows), 0

    with conn.cursor() as cur:
        cur.execute(
            "SELECT ticker FROM index_constituents WHERE index_id=%s AND snapshot_date=%s",
            (index_id, prev_date)
        )
        prev_set = {r[0] for r in cur.fetchall()}

    added_tickers = new_set - prev_set
    removed_tickers = prev_set - new_set

    rows = []
    for t in added_tickers:
        rows.append((index_id, t, "", "ADDED", snap, prev_date))
    for t in removed_tickers:
        rows.append((index_id, t, "", "REMOVED", snap, prev_date))

    if rows:
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT IGNORE INTO constituent_changes "
                "(index_id, ticker, name, change_type, change_date, prev_date) "
                "VALUES (%s,%s,%s,%s,%s,%s)",
                rows
            )
        conn.commit()
    return len(added_tickers), len(removed_tickers)


def _register_stocks(conn, df: pd.DataFrame) -> None:
    rows = []
    for _, r in df.iterrows():
        ticker = r["ticker"]
        exchange = ticker.split(".")[1]   # SH or SZ
        rows.append((ticker, r["name"], r["sector"], exchange))
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO stocks (ticker, name, gics_sector, exchange) "
            "VALUES (%s,%s,%s,%s) "
            "ON DUPLICATE KEY UPDATE name=VALUES(name), gics_sector=VALUES(gics_sector), "
            "exchange=VALUES(exchange)",
            rows
        )
    conn.commit()


def _upsert_index_log(conn, index_id, snap_date, rows_added, added_count, removed_count,
                      status="ok", message=""):
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO index_sync_log
               (index_id, snapshot_date, rows_added, added_count, removed_count, status, message)
               VALUES (%s,%s,%s,%s,%s,%s,%s)
               ON DUPLICATE KEY UPDATE
                 snapshot_date = VALUES(snapshot_date),
                 rows_added    = VALUES(rows_added),
                 added_count   = VALUES(added_count),
                 removed_count = VALUES(removed_count),
                 last_run      = CURRENT_TIMESTAMP,
                 status        = VALUES(status),
                 message       = VALUES(message)
            """,
            (index_id, snap_date, rows_added, added_count, removed_count, status, message)
        )
    conn.commit()
```

- [ ] **Step 4: Run — expect pass**

```bash
pytest tests/test_index_updater_cn.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Smoke test (live akshare)**

```bash
python -c "
from data.index_updater_cn import update_csi800
update_csi800()
"
```

Verify in DB:
```sql
SELECT COUNT(*) FROM index_constituents WHERE index_id='CSI800' AND snapshot_date=CURDATE();
-- Should be ~800
```

- [ ] **Step 6: Commit**

```bash
git add data/index_updater_cn.py tests/test_index_updater_cn.py
git commit -m "data: index_updater_cn — CSI800 constituent snapshot via akshare"
```

---

## Task 13: `data/stock_updater_cn.py` (akshare-only first)

**Files:**
- Create: `/Users/xiaohong/Project/Project_B/data/stock_updater_cn.py`
- Create: `/Users/xiaohong/Project/Project_B/tests/test_stock_updater_cn.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_stock_updater_cn.py
from unittest.mock import patch, MagicMock
import pandas as pd
from datetime import date


def _ak_hist_df():
    return pd.DataFrame({
        "日期":     ["2024-01-02", "2024-01-03"],
        "开盘":     [1700.0, 1710.0],
        "收盘":     [1715.0, 1720.0],
        "最高":     [1720.0, 1725.0],
        "最低":     [1695.0, 1705.0],
        "成交量":   [1000000, 1100000],
        "成交额":   [1.7e9, 1.8e9],
    })


@patch("data.stock_updater_cn.ak.stock_zh_a_hist")
def test_fetch_one_normalizes_columns(mock_ak):
    from data.stock_updater_cn import _fetch_one_akshare
    mock_ak.return_value = _ak_hist_df()
    df = _fetch_one_akshare("600519.SH", date(2024, 1, 1), date(2024, 1, 5))
    assert list(df.columns) == ["ticker", "date", "open", "high", "low", "close", "volume"]
    assert df["ticker"].iloc[0] == "600519.SH"
    assert df["date"].iloc[0] == date(2024, 1, 2)
    assert df["close"].iloc[1] == 1720.0


@patch("data.stock_updater_cn._fetch_one_akshare")
@patch("data.stock_updater_cn.get_conn")
def test_update_prices_writes_and_logs(mock_get_conn, mock_fetch):
    from data.stock_updater_cn import update_prices_batch
    mock_fetch.return_value = pd.DataFrame({
        "ticker": ["600519.SH"], "date": [date(2024, 1, 2)],
        "open": [1700.0], "high": [1720.0], "low": [1695.0],
        "close": [1715.0], "volume": [1000000],
    })
    cur = MagicMock()
    cur.fetchone.return_value = None
    mock_get_conn.return_value.cursor.return_value.__enter__.return_value = cur

    result = update_prices_batch(["600519.SH"])
    assert result["600519.SH"] == "ok"
```

- [ ] **Step 2: Run — expect fail**

```bash
pytest tests/test_stock_updater_cn.py -v
```

- [ ] **Step 3: Implement `data/stock_updater_cn.py`**

```python
"""A-share daily-K updater via akshare (post-adjusted, hfq).

Stores hfq close in `prices.close` (matches yfinance auto-adjusted convention
on the existing US data, even though current US data is raw — known v2 mismatch).
"""

from __future__ import annotations

import logging
import time
from datetime import date, datetime, timedelta
from typing import Dict, List

import akshare as ak
import pandas as pd

from config import (
    HISTORY_YEARS_CN, START_DATE_CN, YF_LOOKBACK_DAYS,
    AKSHARE_RETRY_COUNT, AKSHARE_RETRY_DELAY, AKSHARE_REQUEST_DELAY,
)
from db import get_conn, get_last_sync, set_sync_ok, set_sync_error
from data.base import to_float, to_int
from data.ticker_utils import to_akshare_a

log = logging.getLogger(__name__)


def update_prices_batch(tickers: List[str], full_rebase: bool = False) -> Dict[str, str]:
    """Pull daily K (hfq) for a list of A-share canonical tickers (e.g., 600519.SH).

    Args:
      tickers: canonical A-share tickers
      full_rebase: if True, ignore sync_log and pull from START_DATE_CN

    Returns: {ticker: status}
    """
    if not tickers:
        return {}

    today = date.today()
    end = today
    result: Dict[str, str] = {}

    conn = get_conn()
    try:
        for t in tickers:
            try:
                if full_rebase:
                    start = date.fromisoformat(START_DATE_CN)
                else:
                    last = get_last_sync(conn, t, "price")
                    if last is None:
                        start = date.fromisoformat(START_DATE_CN)
                    else:
                        start = last - timedelta(days=YF_LOOKBACK_DAYS)

                df = _fetch_one_akshare_with_retry(t, start, end)
                if df is None or df.empty:
                    set_sync_error(conn, t, "price", "akshare: no data")
                    result[t] = "no_data"
                    continue

                rows = _save_prices(conn, df)
                set_sync_ok(conn, t, "price", df["date"].max(), rows)
                result[t] = "ok"
                log.info(f"[{t}] 写入 {rows} 行，{df['date'].min()} → {df['date'].max()}")
                time.sleep(AKSHARE_REQUEST_DELAY)
            except Exception as e:
                log.error(f"[{t}] 失败: {e}")
                set_sync_error(conn, t, "price", str(e))
                result[t] = f"error: {e}"
        return result
    finally:
        conn.close()


def _fetch_one_akshare_with_retry(ticker: str, start: date, end: date) -> pd.DataFrame:
    last_exc = None
    for attempt in range(AKSHARE_RETRY_COUNT):
        try:
            return _fetch_one_akshare(ticker, start, end)
        except Exception as e:
            last_exc = e
            if attempt < AKSHARE_RETRY_COUNT - 1:
                wait = AKSHARE_RETRY_DELAY * (2 ** attempt)
                log.warning(f"[{ticker}] akshare attempt {attempt+1} failed: {e}, retry in {wait}s")
                time.sleep(wait)
    raise last_exc


def _fetch_one_akshare(ticker: str, start: date, end: date) -> pd.DataFrame:
    code = to_akshare_a(ticker)
    raw = ak.stock_zh_a_hist(
        symbol=code, period="daily",
        start_date=start.strftime("%Y%m%d"),
        end_date=end.strftime("%Y%m%d"),
        adjust="hfq",
    )
    if raw is None or raw.empty:
        return pd.DataFrame(columns=["ticker", "date", "open", "high", "low", "close", "volume"])

    df = pd.DataFrame({
        "ticker": ticker,
        "date":   pd.to_datetime(raw["日期"]).dt.date,
        "open":   raw["开盘"].astype(float),
        "high":   raw["最高"].astype(float),
        "low":    raw["最低"].astype(float),
        "close":  raw["收盘"].astype(float),
        "volume": raw["成交量"].astype("int64"),
    })
    return df[["ticker", "date", "open", "high", "low", "close", "volume"]]


def _save_prices(conn, df: pd.DataFrame) -> int:
    """INSERT ... ON DUPLICATE KEY UPDATE so rebases overwrite cleanly."""
    sql = """
        INSERT INTO prices (ticker, date, open, high, low, close, volume)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            open=VALUES(open), high=VALUES(high), low=VALUES(low),
            close=VALUES(close), volume=VALUES(volume)
    """
    rows = [
        (
            r.ticker, r.date,
            to_float(r.open), to_float(r.high),
            to_float(r.low), to_float(r.close),
            to_int(r.volume),
        )
        for r in df.itertuples(index=False)
    ]
    with conn.cursor() as cur:
        cur.executemany(sql, rows)
    conn.commit()
    return len(rows)
```

- [ ] **Step 4: Run tests — expect pass**

```bash
pytest tests/test_stock_updater_cn.py -v
```

- [ ] **Step 5: Smoke test (live akshare, single ticker)**

```bash
python -c "
from data.stock_updater_cn import update_prices_batch
print(update_prices_batch(['600519.SH']))
"
```

Verify in DB:
```sql
SELECT MIN(date), MAX(date), COUNT(*) FROM prices WHERE ticker='600519.SH';
-- Expected: 2010-01-04 → today, ~3700 rows
```

- [ ] **Step 6: Commit**

```bash
git add data/stock_updater_cn.py tests/test_stock_updater_cn.py
git commit -m "data: stock_updater_cn — A-share hfq via akshare (single source v1)"
```

---

## Task 14: `data/reconcile.py` (TDD)

**Files:**
- Create: `/Users/xiaohong/Project/Project_B/data/reconcile.py`
- Create: `/Users/xiaohong/Project/Project_B/tests/test_reconcile.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_reconcile.py
import pandas as pd
from datetime import date


def _df(closes, dates=None):
    dates = dates or [date(2024, 1, d) for d in range(2, 2 + len(closes))]
    return pd.DataFrame({
        "ticker": ["600519.SH"] * len(closes),
        "date":   dates,
        "open":   [c - 1 for c in closes],
        "high":   [c + 5 for c in closes],
        "low":    [c - 5 for c in closes],
        "close":  closes,
        "volume": [1000] * len(closes),
    })


def test_both_sources_agree_uses_primary():
    from data.reconcile import reconcile_two_sources
    a = _df([1700.0, 1710.0])
    b = _df([1700.5, 1710.3])  # within 0.5%
    merged, mismatches = reconcile_two_sources(a, b, tolerance=0.005)
    assert len(merged) == 2
    assert merged["close"].tolist() == [1700.0, 1710.0]   # primary wins
    assert mismatches == []


def test_disagreement_logged_but_primary_wins():
    from data.reconcile import reconcile_two_sources
    a = _df([1700.0, 1710.0])
    b = _df([1700.0, 1900.0])   # day 2 diverges 11%
    merged, mismatches = reconcile_two_sources(a, b, tolerance=0.005)
    assert merged["close"].tolist() == [1700.0, 1710.0]
    assert len(mismatches) == 1
    assert mismatches[0]["date"] == date(2024, 1, 3)
    assert mismatches[0]["primary"] == 1710.0
    assert mismatches[0]["secondary"] == 1900.0


def test_only_primary_passes_through():
    from data.reconcile import reconcile_two_sources
    a = _df([1700.0])
    b = pd.DataFrame(columns=a.columns)
    merged, mismatches = reconcile_two_sources(a, b)
    assert len(merged) == 1
    assert mismatches == []


def test_only_secondary_used_when_primary_empty():
    from data.reconcile import reconcile_two_sources
    a = pd.DataFrame(columns=["ticker", "date", "open", "high", "low", "close", "volume"])
    b = _df([1700.0])
    merged, mismatches = reconcile_two_sources(a, b)
    assert len(merged) == 1
    assert merged["close"].iloc[0] == 1700.0
```

- [ ] **Step 2: Run — expect fail**

```bash
pytest tests/test_reconcile.py -v
```

- [ ] **Step 3: Implement `data/reconcile.py`**

```python
"""Two-source reconciliation for A-share / HK daily-K data.

Strategy:
  - For each (ticker, date) row, compare close.
  - Within tolerance: take primary's row.
  - Beyond tolerance: log mismatch, still take primary's row.
  - Only one source has the row: pass through.
"""

from __future__ import annotations

import logging
from typing import List, Tuple

import pandas as pd

from config import RECONCILE_PRICE_TOLERANCE

log = logging.getLogger(__name__)


def reconcile_two_sources(
    primary: pd.DataFrame,
    secondary: pd.DataFrame,
    tolerance: float = RECONCILE_PRICE_TOLERANCE,
) -> Tuple[pd.DataFrame, List[dict]]:
    """Merge two daily-K DataFrames by (ticker, date), preferring primary.

    Returns:
      (merged_df, mismatches)  — mismatches: list of {ticker, date, primary, secondary}
    """
    cols = ["ticker", "date", "open", "high", "low", "close", "volume"]

    if primary.empty and secondary.empty:
        return pd.DataFrame(columns=cols), []

    if primary.empty:
        return secondary[cols].reset_index(drop=True), []

    if secondary.empty:
        return primary[cols].reset_index(drop=True), []

    p = primary.set_index(["ticker", "date"])
    s = secondary.set_index(["ticker", "date"])

    common = p.index.intersection(s.index)
    only_secondary = s.index.difference(p.index)

    mismatches: List[dict] = []
    for idx in common:
        p_close = float(p.loc[idx, "close"])
        s_close = float(s.loc[idx, "close"])
        if p_close == 0:
            continue
        if abs(p_close - s_close) / p_close > tolerance:
            ticker, dt = idx
            log.warning(
                f"[reconcile] {ticker} {dt}: primary close={p_close} vs secondary={s_close} "
                f"(diff {abs(p_close-s_close)/p_close*100:.2f}%)"
            )
            mismatches.append({
                "ticker": ticker, "date": dt,
                "primary": p_close, "secondary": s_close,
            })

    # Build merged: all primary + secondary-only
    merged = pd.concat([
        p,
        s.loc[only_secondary] if len(only_secondary) > 0 else pd.DataFrame(),
    ])
    merged = merged.reset_index().sort_values(["ticker", "date"]).reset_index(drop=True)
    return merged[cols], mismatches
```

- [ ] **Step 4: Run — expect pass**

```bash
pytest tests/test_reconcile.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add data/reconcile.py tests/test_reconcile.py
git commit -m "data: reconcile.py — two-source diff with tolerance and warnings"
```

---

## Task 15: Integrate efinance into `stock_updater_cn`

**Files:**
- Modify: `/Users/xiaohong/Project/Project_B/data/stock_updater_cn.py`
- Modify: `/Users/xiaohong/Project/Project_B/tests/test_stock_updater_cn.py` (add test)

- [ ] **Step 1: Add failing test for efinance reconciliation in backfill mode**

Append to `tests/test_stock_updater_cn.py`:

```python
@patch("data.stock_updater_cn._fetch_one_efinance")
@patch("data.stock_updater_cn._fetch_one_akshare")
@patch("data.stock_updater_cn.get_conn")
def test_backfill_calls_both_sources_and_reconciles(mock_conn, mock_ak, mock_ef):
    from data.stock_updater_cn import update_prices_batch
    mock_ak.return_value = pd.DataFrame({
        "ticker": ["600519.SH"], "date": [date(2024, 1, 2)],
        "open": [1700.0], "high": [1720.0], "low": [1695.0],
        "close": [1715.0], "volume": [1000000],
    })
    mock_ef.return_value = pd.DataFrame({
        "ticker": ["600519.SH"], "date": [date(2024, 1, 2)],
        "open": [1700.5], "high": [1721.0], "low": [1696.0],
        "close": [1715.3], "volume": [1000100],
    })
    cur = MagicMock()
    cur.fetchone.return_value = None  # last_sync = None → backfill mode
    mock_conn.return_value.cursor.return_value.__enter__.return_value = cur

    result = update_prices_batch(["600519.SH"])
    assert result["600519.SH"] == "ok"
    mock_ef.assert_called_once()  # backfill triggers efinance
```

- [ ] **Step 2: Run — expect fail** (efinance not yet integrated)

- [ ] **Step 3: Modify `stock_updater_cn.py`** — add efinance fetcher and integrate into backfill path

Add at top:
```python
import efinance as ef
from data.reconcile import reconcile_two_sources
from data.ticker_utils import to_efinance_a
```

Add function after `_fetch_one_akshare`:
```python
def _fetch_one_efinance(ticker: str, start: date, end: date) -> pd.DataFrame:
    """efinance A-share post-adjusted daily K. klt=101 (daily), fqt=2 (post-adjusted)."""
    code = to_efinance_a(ticker)
    raw = ef.stock.get_quote_history(
        stock_codes=code,
        beg=start.strftime("%Y%m%d"),
        end=end.strftime("%Y%m%d"),
        klt=101, fqt=2,
    )
    if raw is None or len(raw) == 0:
        return pd.DataFrame(columns=["ticker", "date", "open", "high", "low", "close", "volume"])

    df = pd.DataFrame({
        "ticker": ticker,
        "date":   pd.to_datetime(raw["日期"]).dt.date,
        "open":   raw["开盘"].astype(float),
        "high":   raw["最高"].astype(float),
        "low":    raw["最低"].astype(float),
        "close":  raw["收盘"].astype(float),
        "volume": raw["成交量"].astype("int64"),
    })
    return df[["ticker", "date", "open", "high", "low", "close", "volume"]]
```

Modify `update_prices_batch` body (the per-ticker loop): when `last is None` (backfill mode), pull both sources and reconcile:

```python
            # Replace the existing "df = _fetch_one_akshare_with_retry(...)" line with:
            df_a = _fetch_one_akshare_with_retry(t, start, end)
            is_backfill = full_rebase or last is None
            if is_backfill:
                try:
                    df_b = _fetch_one_efinance(t, start, end)
                except Exception as e:
                    log.warning(f"[{t}] efinance failed (continue with akshare): {e}")
                    df_b = pd.DataFrame(columns=df_a.columns)
                df, mismatches = reconcile_two_sources(df_a, df_b)
                if mismatches:
                    log.warning(f"[{t}] {len(mismatches)} reconcile mismatches (logged above)")
            else:
                df = df_a
```

(Replace ONLY the `df = _fetch_one_akshare_with_retry(...)` line; keep the rest of the loop body — `if df is None or df.empty: ...` and onwards — unchanged.)

- [ ] **Step 4: Run — expect pass**

```bash
pytest tests/test_stock_updater_cn.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Smoke test against live (single ticker, backfill path)**

```bash
# Wipe sync_log for test ticker so it goes through backfill
python -c "
from db import execute
execute('DELETE FROM sync_log WHERE ticker=%s', ('600519.SH',))
"
python -c "
from data.stock_updater_cn import update_prices_batch
print(update_prices_batch(['600519.SH']))
"
```

Expected: `ok`. Watch for any reconcile WARNING lines in stdout.

- [ ] **Step 6: Commit**

```bash
git add data/stock_updater_cn.py tests/test_stock_updater_cn.py
git commit -m "data: stock_updater_cn — add efinance reconciliation in backfill mode"
```

---

## Task 16: `data/market_cn.py` module wrapper

**Files:**
- Create: `/Users/xiaohong/Project/Project_B/data/market_cn.py`

- [ ] **Step 1: Implement**

```python
"""A-share market module: adapts CN ingest to Pipeline protocol."""

from __future__ import annotations

import logging
from datetime import date
from typing import Optional

import akshare as ak
import pandas as pd

from db import get_conn, get_index_tickers, query, execute
from data import index_updater_cn
from data import stock_updater_cn
from data.base import to_float

log = logging.getLogger(__name__)

market_id = "cn"


def update_index() -> tuple[list[str], int, int]:
    conn = get_conn()
    try:
        prev = set(_latest_snapshot_tickers(conn, "CSI800"))
    finally:
        conn.close()

    index_updater_cn.update_csi800()

    conn = get_conn()
    try:
        curr = set(_latest_snapshot_tickers(conn, "CSI800"))
    finally:
        conn.close()
    new_added = sorted(curr - prev)
    return new_added, len(curr), len(prev - curr)


def list_active_tickers() -> list[str]:
    return get_index_tickers("CSI800")


def backfill_new(new_tickers: list[str]) -> dict[str, str]:
    if not new_tickers:
        return {}
    return stock_updater_cn.update_prices_batch(new_tickers)


def incremental(tickers: list[str]) -> dict[str, str]:
    if not tickers:
        return {}
    return stock_updater_cn.update_prices_batch(tickers)


def update_index_price() -> int:
    """中证800 指数 close via akshare (sh000906)."""
    last = query(
        "SELECT MAX(date) AS d FROM index_prices WHERE index_id=%s", ("CSI800",)
    )
    last_date = last[0]["d"] if last and last[0]["d"] else None

    raw = ak.stock_zh_index_daily(symbol="sh000906")
    if raw is None or raw.empty:
        return 0

    df = pd.DataFrame({
        "date":  pd.to_datetime(raw["date"]).dt.date,
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


def rebase(tickers: Optional[list[str]] = None) -> dict[str, str]:
    """Full re-pull from START_DATE_CN to fix hfq drift."""
    targets = tickers if tickers else list_active_tickers()
    return stock_updater_cn.update_prices_batch(targets, full_rebase=True)


def _latest_snapshot_tickers(conn, index_id: str) -> list[str]:
    rows = query(
        """SELECT DISTINCT ticker FROM index_constituents
           WHERE index_id=%s AND snapshot_date = (
             SELECT MAX(snapshot_date) FROM index_constituents WHERE index_id=%s
           )""",
        (index_id, index_id)
    )
    return [r["ticker"] for r in rows]
```

- [ ] **Step 2: Smoke test**

```bash
python main.py daily --market cn --code 600519.SH
```

Expected: log "incremental only" path completes for one ticker.

- [ ] **Step 3: Commit**

```bash
git add data/market_cn.py
git commit -m "data: market_cn module adapting A-share ingest to Pipeline"
```

---

## Task 17: `data/index_updater_hk.py` (HSI)

**Files:**
- Create: `/Users/xiaohong/Project/Project_B/data/index_updater_hk.py`
- Create: `/Users/xiaohong/Project/Project_B/tests/test_index_updater_hk.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_index_updater_hk.py
from unittest.mock import patch
import pandas as pd


def _ak_hsi_df():
    """akshare HK HSI components return shape — column names differ from A-share."""
    return pd.DataFrame({
        "代码":  ["00700", "09988", "00005"],
        "名称":  ["腾讯控股", "阿里巴巴-W", "汇丰控股"],
    })


@patch("data.index_updater_hk.ak.stock_hk_index_components_em")
def test_fetch_hsi_normalizes_to_hk_canonical(mock_ak):
    from data.index_updater_hk import _fetch_hsi
    mock_ak.return_value = _ak_hsi_df()
    df = _fetch_hsi()
    assert set(df["ticker"]) == {"00700.HK", "09988.HK", "00005.HK"}
    assert "name" in df.columns
```

- [ ] **Step 2: Run — expect fail**

- [ ] **Step 3: Implement `data/index_updater_hk.py`**

Use the same structure as `index_updater_cn.py`, replacing the fetcher. Keep `_save_snapshot`, `_detect_changes`, `_register_stocks`, `_upsert_index_log`, `_get_last_snapshot_date` IDENTICAL to `index_updater_cn.py` (same SQL semantics) — copy them verbatim.

```python
"""HSI (恒生指数) constituent updater via akshare."""

from __future__ import annotations

import logging
from datetime import date
from typing import Optional, Set, Tuple

import akshare as ak
import pandas as pd

from db import get_conn
from data.ticker_utils import from_akshare_hk

log = logging.getLogger(__name__)

INDEX_ID = "HSI"


def update_hsi() -> None:
    conn = get_conn()
    try:
        prev_date = _get_last_snapshot_date(conn, INDEX_ID)
        if prev_date == date.today():
            log.info(f"[{INDEX_ID}] 今日已更新，跳过")
            return

        df = _fetch_hsi()
        if df is None or df.empty:
            log.error(f"[{INDEX_ID}] 获取数据失败")
            _upsert_index_log(conn, INDEX_ID, date.today(), 0, 0, 0, "error", "无数据")
            return

        snap = date.today()
        new_set = set(df["ticker"].unique())
        inserted = _save_snapshot(conn, df, INDEX_ID, snap)
        added, removed = _detect_changes(conn, INDEX_ID, snap, new_set, prev_date)
        _register_stocks(conn, df)
        _upsert_index_log(conn, INDEX_ID, snap, inserted, added, removed)
        log.info(f"[{INDEX_ID}] 完成 {snap}: {inserted}条 +{added} -{removed}")
    except Exception as e:
        log.error(f"[{INDEX_ID}] 更新失败: {e}")
        _upsert_index_log(conn, INDEX_ID, date.today(), 0, 0, 0, "error", str(e))
    finally:
        conn.close()


def _fetch_hsi() -> pd.DataFrame:
    raw = ak.stock_hk_index_components_em(symbol="HSI")
    df = pd.DataFrame({
        "ticker": [from_akshare_hk(c) for c in raw["代码"].astype(str)],
        "name":   raw["名称"],
        "sector": "",
    })
    return df


# --- copy verbatim from data/index_updater_cn.py ---
def _get_last_snapshot_date(conn, index_id):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT MAX(snapshot_date) FROM index_constituents WHERE index_id=%s",
            (index_id,)
        )
        row = cur.fetchone()
    return row[0] if row and row[0] else None


def _save_snapshot(conn, df, index_id, snap):
    rows = [(index_id, snap, r["ticker"], r["name"], r.get("sector", ""))
            for _, r in df.iterrows()]
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT IGNORE INTO index_constituents "
            "(index_id, snapshot_date, ticker, name, sector) VALUES (%s,%s,%s,%s,%s)",
            rows
        )
    conn.commit()
    return len(rows)


def _detect_changes(conn, index_id, snap, new_set, prev_date):
    if prev_date is None:
        rows = [(index_id, t, "", "ADDED", snap, None) for t in new_set]
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT IGNORE INTO constituent_changes "
                "(index_id, ticker, name, change_type, change_date, prev_date) "
                "VALUES (%s,%s,%s,%s,%s,%s)",
                rows
            )
        conn.commit()
        return len(rows), 0

    with conn.cursor() as cur:
        cur.execute(
            "SELECT ticker FROM index_constituents WHERE index_id=%s AND snapshot_date=%s",
            (index_id, prev_date)
        )
        prev_set = {r[0] for r in cur.fetchall()}

    added = new_set - prev_set
    removed = prev_set - new_set
    rows = ([(index_id, t, "", "ADDED", snap, prev_date) for t in added]
            + [(index_id, t, "", "REMOVED", snap, prev_date) for t in removed])
    if rows:
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT IGNORE INTO constituent_changes "
                "(index_id, ticker, name, change_type, change_date, prev_date) "
                "VALUES (%s,%s,%s,%s,%s,%s)",
                rows
            )
        conn.commit()
    return len(added), len(removed)


def _register_stocks(conn, df):
    rows = [(r["ticker"], r["name"], r.get("sector", ""), "HK")
            for _, r in df.iterrows()]
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO stocks (ticker, name, gics_sector, exchange) "
            "VALUES (%s,%s,%s,%s) "
            "ON DUPLICATE KEY UPDATE name=VALUES(name), gics_sector=VALUES(gics_sector), "
            "exchange=VALUES(exchange)",
            rows
        )
    conn.commit()


def _upsert_index_log(conn, index_id, snap_date, rows_added, added_count, removed_count,
                      status="ok", message=""):
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO index_sync_log
               (index_id, snapshot_date, rows_added, added_count, removed_count, status, message)
               VALUES (%s,%s,%s,%s,%s,%s,%s)
               ON DUPLICATE KEY UPDATE
                 snapshot_date = VALUES(snapshot_date),
                 rows_added    = VALUES(rows_added),
                 added_count   = VALUES(added_count),
                 removed_count = VALUES(removed_count),
                 last_run      = CURRENT_TIMESTAMP,
                 status        = VALUES(status),
                 message       = VALUES(message)
            """,
            (index_id, snap_date, rows_added, added_count, removed_count, status, message)
        )
    conn.commit()
```

- [ ] **Step 4: Run — expect pass**

```bash
pytest tests/test_index_updater_hk.py -v
```

- [ ] **Step 5: Smoke test (live)**

```bash
python -c "
from data.index_updater_hk import update_hsi
update_hsi()
"
```

Verify:
```sql
SELECT COUNT(*) FROM index_constituents WHERE index_id='HSI' AND snapshot_date=CURDATE();
-- Expected ~80
```

- [ ] **Step 6: Commit**

```bash
git add data/index_updater_hk.py tests/test_index_updater_hk.py
git commit -m "data: index_updater_hk — HSI constituent snapshot via akshare"
```

---

## Task 18: `data/stock_updater_hk.py`

**Files:**
- Create: `/Users/xiaohong/Project/Project_B/data/stock_updater_hk.py`
- Create: `/Users/xiaohong/Project/Project_B/tests/test_stock_updater_hk.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_stock_updater_hk.py
from unittest.mock import patch, MagicMock
import pandas as pd
from datetime import date


def _ak_hk_hist_df():
    """akshare stock_hk_daily output shape."""
    return pd.DataFrame({
        "date":   ["2024-01-02", "2024-01-03"],
        "open":   [310.0, 312.0],
        "high":   [315.0, 316.0],
        "low":    [308.0, 310.0],
        "close":  [314.0, 315.0],
        "volume": [10_000_000, 11_000_000],
    })


@patch("data.stock_updater_hk.ak.stock_hk_daily")
def test_fetch_normalizes_columns_and_filters_range(mock_ak):
    from data.stock_updater_hk import _fetch_one_akshare
    mock_ak.return_value = _ak_hk_hist_df()
    df = _fetch_one_akshare("00700.HK", date(2024, 1, 1), date(2024, 1, 5))
    assert list(df.columns) == ["ticker", "date", "open", "high", "low", "close", "volume"]
    assert df["ticker"].iloc[0] == "00700.HK"
    assert all(df["date"] >= date(2024, 1, 1))
    assert all(df["date"] <= date(2024, 1, 5))
```

- [ ] **Step 2: Run — expect fail**

- [ ] **Step 3: Implement `data/stock_updater_hk.py`**

Mostly mirrors `stock_updater_cn.py`, but akshare HK doesn't accept start/end → filter locally.

```python
"""HK daily-K updater via akshare (post-adjusted, hfq).

akshare's stock_hk_daily does NOT accept start/end; pull all and filter locally.
"""

from __future__ import annotations

import logging
import time
from datetime import date, timedelta
from typing import Dict, List, Optional

import akshare as ak
import efinance as ef
import pandas as pd

from config import (
    HISTORY_YEARS_HK, START_DATE_HK, YF_LOOKBACK_DAYS,
    AKSHARE_RETRY_COUNT, AKSHARE_RETRY_DELAY, AKSHARE_REQUEST_DELAY,
)
from db import get_conn, get_last_sync, set_sync_ok, set_sync_error
from data.base import to_float, to_int
from data.ticker_utils import to_akshare_hk, to_efinance_hk
from data.reconcile import reconcile_two_sources

log = logging.getLogger(__name__)


def update_prices_batch(tickers: List[str], full_rebase: bool = False) -> Dict[str, str]:
    if not tickers:
        return {}
    today = date.today()
    end = today
    result: Dict[str, str] = {}

    conn = get_conn()
    try:
        for t in tickers:
            try:
                if full_rebase:
                    start = date.fromisoformat(START_DATE_HK)
                    last = None
                else:
                    last = get_last_sync(conn, t, "price")
                    if last is None:
                        start = date.fromisoformat(START_DATE_HK)
                    else:
                        start = last - timedelta(days=YF_LOOKBACK_DAYS)

                df_a = _fetch_one_akshare_with_retry(t, start, end)
                is_backfill = full_rebase or last is None
                if is_backfill:
                    try:
                        df_b = _fetch_one_efinance(t, start, end)
                    except Exception as e:
                        log.warning(f"[{t}] efinance failed: {e}")
                        df_b = pd.DataFrame(columns=df_a.columns)
                    df, mismatches = reconcile_two_sources(df_a, df_b)
                    if mismatches:
                        log.warning(f"[{t}] {len(mismatches)} reconcile mismatches")
                else:
                    df = df_a

                if df is None or df.empty:
                    set_sync_error(conn, t, "price", "akshare/efinance: no data")
                    result[t] = "no_data"
                    continue

                rows = _save_prices(conn, df)
                set_sync_ok(conn, t, "price", df["date"].max(), rows)
                result[t] = "ok"
                log.info(f"[{t}] 写入 {rows} 行，{df['date'].min()} → {df['date'].max()}")
                time.sleep(AKSHARE_REQUEST_DELAY)
            except Exception as e:
                log.error(f"[{t}] 失败: {e}")
                set_sync_error(conn, t, "price", str(e))
                result[t] = f"error: {e}"
        return result
    finally:
        conn.close()


def _fetch_one_akshare_with_retry(ticker: str, start: date, end: date) -> pd.DataFrame:
    last_exc = None
    for attempt in range(AKSHARE_RETRY_COUNT):
        try:
            return _fetch_one_akshare(ticker, start, end)
        except Exception as e:
            last_exc = e
            if attempt < AKSHARE_RETRY_COUNT - 1:
                time.sleep(AKSHARE_RETRY_DELAY * (2 ** attempt))
    raise last_exc


def _fetch_one_akshare(ticker: str, start: date, end: date) -> pd.DataFrame:
    code = to_akshare_hk(ticker)
    raw = ak.stock_hk_daily(symbol=code, adjust="hfq")
    if raw is None or len(raw) == 0:
        return pd.DataFrame(columns=["ticker", "date", "open", "high", "low", "close", "volume"])

    df = pd.DataFrame({
        "ticker": ticker,
        "date":   pd.to_datetime(raw["date"]).dt.date,
        "open":   raw["open"].astype(float),
        "high":   raw["high"].astype(float),
        "low":    raw["low"].astype(float),
        "close":  raw["close"].astype(float),
        "volume": raw["volume"].astype("int64"),
    })
    df = df[(df["date"] >= start) & (df["date"] <= end)]
    return df[["ticker", "date", "open", "high", "low", "close", "volume"]].reset_index(drop=True)


def _fetch_one_efinance(ticker: str, start: date, end: date) -> pd.DataFrame:
    code = to_efinance_hk(ticker)
    raw = ef.stock.get_quote_history(
        stock_codes=code,
        beg=start.strftime("%Y%m%d"),
        end=end.strftime("%Y%m%d"),
        klt=101, fqt=2,
    )
    if raw is None or len(raw) == 0:
        return pd.DataFrame(columns=["ticker", "date", "open", "high", "low", "close", "volume"])

    df = pd.DataFrame({
        "ticker": ticker,
        "date":   pd.to_datetime(raw["日期"]).dt.date,
        "open":   raw["开盘"].astype(float),
        "high":   raw["最高"].astype(float),
        "low":    raw["最低"].astype(float),
        "close":  raw["收盘"].astype(float),
        "volume": raw["成交量"].astype("int64"),
    })
    return df[["ticker", "date", "open", "high", "low", "close", "volume"]]


def _save_prices(conn, df: pd.DataFrame) -> int:
    sql = """
        INSERT INTO prices (ticker, date, open, high, low, close, volume)
        VALUES (%s,%s,%s,%s,%s,%s,%s)
        ON DUPLICATE KEY UPDATE
            open=VALUES(open), high=VALUES(high), low=VALUES(low),
            close=VALUES(close), volume=VALUES(volume)
    """
    rows = [
        (r.ticker, r.date,
         to_float(r.open), to_float(r.high), to_float(r.low),
         to_float(r.close), to_int(r.volume))
        for r in df.itertuples(index=False)
    ]
    with conn.cursor() as cur:
        cur.executemany(sql, rows)
    conn.commit()
    return len(rows)
```

- [ ] **Step 4: Run — expect pass**

```bash
pytest tests/test_stock_updater_hk.py -v
```

- [ ] **Step 5: Smoke test (live)**

```bash
python -c "
from data.stock_updater_hk import update_prices_batch
print(update_prices_batch(['00700.HK']))
"
```

Verify:
```sql
SELECT MIN(date), MAX(date), COUNT(*) FROM prices WHERE ticker='00700.HK';
```

- [ ] **Step 6: Commit**

```bash
git add data/stock_updater_hk.py tests/test_stock_updater_hk.py
git commit -m "data: stock_updater_hk — HK hfq via akshare + efinance reconcile"
```

---

## Task 19: `data/market_hk.py` module wrapper

**Files:**
- Create: `/Users/xiaohong/Project/Project_B/data/market_hk.py`

- [ ] **Step 1: Implement** (mirrors `market_cn.py`)

```python
"""HK market module: adapts HSI ingest to Pipeline protocol."""

from __future__ import annotations

import logging
from typing import Optional

import akshare as ak
import pandas as pd

from db import get_conn, get_index_tickers, query, execute
from data import index_updater_hk
from data import stock_updater_hk
from data.base import to_float

log = logging.getLogger(__name__)

market_id = "hk"


def update_index() -> tuple[list[str], int, int]:
    conn = get_conn()
    try:
        prev = set(_latest_snapshot_tickers(conn, "HSI"))
    finally:
        conn.close()

    index_updater_hk.update_hsi()

    conn = get_conn()
    try:
        curr = set(_latest_snapshot_tickers(conn, "HSI"))
    finally:
        conn.close()
    new_added = sorted(curr - prev)
    return new_added, len(curr), len(prev - curr)


def list_active_tickers() -> list[str]:
    return get_index_tickers("HSI")


def backfill_new(new_tickers: list[str]) -> dict[str, str]:
    if not new_tickers:
        return {}
    return stock_updater_hk.update_prices_batch(new_tickers)


def incremental(tickers: list[str]) -> dict[str, str]:
    if not tickers:
        return {}
    return stock_updater_hk.update_prices_batch(tickers)


def update_index_price() -> int:
    last = query(
        "SELECT MAX(date) AS d FROM index_prices WHERE index_id=%s", ("HSI",)
    )
    last_date = last[0]["d"] if last and last[0]["d"] else None

    raw = ak.stock_hk_index_daily_em(symbol="HSI")
    if raw is None or raw.empty:
        return 0

    df = pd.DataFrame({
        "date":  pd.to_datetime(raw["date"]).dt.date,
        "close": raw["latest"].astype(float) if "latest" in raw.columns else raw["close"].astype(float),
    })
    if last_date:
        df = df[df["date"] > last_date]
    if df.empty:
        return 0

    rows = [(r.date, "HSI", to_float(r.close)) for r in df.itertuples(index=False)]
    return execute(
        "INSERT IGNORE INTO index_prices (date, index_id, close) VALUES (%s,%s,%s)",
        rows, many=True,
    )


def rebase(tickers: Optional[list[str]] = None) -> dict[str, str]:
    targets = tickers if tickers else list_active_tickers()
    return stock_updater_hk.update_prices_batch(targets, full_rebase=True)


def _latest_snapshot_tickers(conn, index_id: str) -> list[str]:
    rows = query(
        """SELECT DISTINCT ticker FROM index_constituents
           WHERE index_id=%s AND snapshot_date = (
             SELECT MAX(snapshot_date) FROM index_constituents WHERE index_id=%s
           )""",
        (index_id, index_id)
    )
    return [r["ticker"] for r in rows]
```

- [ ] **Step 2: Smoke test**

```bash
python main.py daily --market hk --code 00700.HK
```

- [ ] **Step 3: Commit**

```bash
git add data/market_hk.py
git commit -m "data: market_hk module adapting HK ingest to Pipeline"
```

---

## Task 20: `scripts/daily_update.sh`

**Files:**
- Create: `/Users/xiaohong/Project/Project_B/scripts/daily_update.sh`

- [ ] **Step 1: Write the script**

```bash
#!/usr/bin/env bash
# scripts/daily_update.sh — local cron wrapper

set -euo pipefail

PROJECT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT"

LOG_DIR="$PROJECT/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/daily-$(date +%Y-%m-%d).log"

# Activate venv if present
if [ -d "$PROJECT/.venv" ]; then
    # shellcheck disable=SC1091
    source "$PROJECT/.venv/bin/activate"
fi

echo "=== $(date) === daily ingest ===" | tee -a "$LOG_FILE"
python main.py daily 2>&1 | tee -a "$LOG_FILE"
echo "=== $(date) === done ===" | tee -a "$LOG_FILE"
```

- [ ] **Step 2: chmod and smoke**

```bash
chmod +x scripts/daily_update.sh
./scripts/daily_update.sh
```

Expected: pipeline runs, log appears at `logs/daily-YYYY-MM-DD.log`.

- [ ] **Step 3: Commit**

```bash
git add scripts/daily_update.sh
git commit -m "scripts: daily_update.sh wrapper writes to logs/"
```

---

## Task 21: End-to-end verification

**Files:** none (validation only)

- [ ] **Step 1: Run full unit test suite**

```bash
pytest -v
```

Expected: all green except possibly skipped smoke tests if NAS unreachable.

- [ ] **Step 2: Idempotency check**

```bash
python main.py daily --market cn --code 600519.SH
python main.py daily --market cn --code 600519.SH
```

Verify in DB:
```sql
SELECT rows_added, last_run FROM sync_log
WHERE ticker='600519.SH' AND data_type='price';
-- Second run rows_added should be small (only LOOKBACK window)
```

- [ ] **Step 3: Init + indices verification**

```bash
python main.py init
```

```sql
SELECT * FROM indices;
-- Expected: SP500, CSI800, HSI rows
```

- [ ] **Step 4: Single-ticker full test for each market**

```bash
python main.py daily --market us  --code AAPL
python main.py daily --market cn  --code 600519.SH
python main.py daily --market hk  --code 00700.HK
```

```sql
SELECT ticker, MIN(date), MAX(date), COUNT(*) FROM prices
WHERE ticker IN ('AAPL', '600519.SH', '00700.HK')
GROUP BY ticker;
```

- [ ] **Step 5: Rebase test**

```bash
python main.py rebase --market cn --code 600519.SH
```

Expected: output mentions "rebase 1 tickers". Check `prices.close` for very early date may be slightly different from before rebase (factor refreshed).

- [ ] **Step 6: Sample data spot-check (manual)**

Open东方财富网 for `贵州茅台 600519`, switch to "**后复权**" mode, pick any date with data in our DB, confirm close matches within rounding.

- [ ] **Step 7: Status command**

```bash
python main.py status
```

Expected: stocks/prices/breadth/errors counts printed.

- [ ] **Step 8: Commit any final fixes**

If any failures during validation lead to fixes, commit them now.

---

## Task 22: Complete `README.md`

**Files:**
- Modify: `/Users/xiaohong/Project/Project_B/README.md`

- [ ] **Step 1: Write the full README**

```markdown
# Project_B — Unified Stocks Ingest (US + A股 + 港股)

Daily K-line ingest service. Pulls from yfinance (US) + akshare/efinance (A股, 港股) and writes
to the shared NAS MariaDB (`stocks` database, schema lives at
`/Volumes/home/stock_system/sql/schema_full.sql`).

## Markets

| Market | Index           | Source(s)             | Adjustment      | History |
|--------|-----------------|-----------------------|-----------------|---------|
| US     | SP500           | yfinance              | raw (current)   | 5 yrs   |
| 中国 A  | CSI800 (中证800) | akshare + efinance    | hfq (post-adj)  | 15 yrs  |
| 港股   | HSI (恒生)       | akshare + efinance    | hfq (post-adj)  | 15 yrs  |

> **Storage convention**: `prices.close` holds raw for US (legacy) and hfq for A/HK. Backtests
> need to know per-market basis. Future v2 may unify by switching US to auto-adjusted.

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # fill in DB_PASSWORD
chmod 600 .env
python main.py init   # one-time: insert CSI800/HSI rows in `indices` table
```

## CLI

```bash
python main.py daily                    # all markets, full pipeline
python main.py daily --market cn        # only A股
python main.py daily --code 600519.SH   # only one ticker (incremental, debug)
python main.py rebase --market cn       # full re-pull (fix hfq factor drift)
python main.py status                   # summary
```

## hfq factor drift and rebase

A股 / HK post-adjusted prices use today's cumulative dividend/split factor as the anchor. When
a new ex-dividend or split happens, **all historical hfq prices change proportionally**. Because
returns between any two dates are unchanged by uniform rescaling, daily incremental ingest is
fine for normal usage. After a dividend wave (typically Apr–Jul for A股), run `rebase` to
re-pull the entire history and overwrite with the latest factor:

```bash
python main.py rebase --market cn   # ~30-60 min for ~800 tickers
python main.py rebase --market hk   # ~5-10 min for ~80 tickers
```

## Architecture

- `main.py` — CLI dispatcher
- `data/pipeline.py` — generic per-market `Pipeline(market_module).daily()` orchestrator
- `data/market_us.py`, `market_cn.py`, `market_hk.py` — per-market adapters
- `data/index_updater_*.py` — constituent snapshot + change detection
- `data/stock_updater_*.py` — per-ticker daily-K fetch + DB write
- `data/reconcile.py` — two-source diff with tolerance (used in A/HK backfill)
- `data/ticker_utils.py` — canonical ticker format conversion
- `db.py` — DB connection + sync_log helpers (ported from stock_system)
- `data/base.py` — HTTP retry + rate limiter + type converters (ported)

## Coexistence with `/Volumes/home/stock_system`

`Project_B` writes ingest data; `/Volumes/home/stock_system` keeps Streamlit UI / analysis /
market_breadth. Both read the same DB, no duplication.

## Run tests

```bash
pytest                       # all tests
pytest -m "not smoke"        # skip live-DB tests
```
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: complete README with setup, CLI, rebase, architecture"
```

---

## Self-Review Checklist (already run)

**1. Spec coverage:**
- ✅ Per-market ingest (US/CN/HK): Tasks 7, 13, 18
- ✅ Constituent snapshots + change detection: Tasks 8, 12, 17
- ✅ Index price ingest: Tasks 10, 16, 19 (each market module's `update_index_price`)
- ✅ Pipeline (Step 1/2/3/4): Task 9
- ✅ CLI subcommands (init/daily/rebase/status): Task 11
- ✅ hfq rebase: Tasks 13 (`full_rebase` flag), 16 (`market_cn.rebase`), 19 (`market_hk.rebase`)
- ✅ Two-source reconciliation: Tasks 14, 15, 18
- ✅ dotenv-driven config: Task 3
- ✅ DB time zone fix: Task 4
- ✅ Tests: TDD throughout, plus integration smoke in Task 21
- ✅ README + scripts/daily_update.sh: Tasks 20, 22

**2. Placeholder scan:** No "TBD", "implement later", or vague steps. Every code/test step shows actual code.

**3. Type consistency:**
- `Market` enum used in `ticker_utils` — consumed nowhere yet, that's OK
- Function signatures: `update_prices_batch(tickers, full_rebase)` consistent in CN and HK
- Pipeline protocol: `update_index → (list, int, int)`, `list_active_tickers → list`, etc., consistent across `market_us`, `market_cn`, `market_hk`
- `_save_prices` in CN/HK uses `ON DUPLICATE KEY UPDATE` (because rebase overwrites); US uses `INSERT IGNORE` (legacy, no rebase)

**4. Ambiguity:** None found in re-read.

---

## Out of Scope (per spec, NOT in any task above)

- Minute / Tick data
- Financial data (`sync_log.data_type` enum reserves `financial`/`stock_info`)
- US `auto_adjust=True` switch + historical re-pull (v2)
- Historical PIT constituent tracking (survivorship bias accepted)
- Streamlit UI / `market_breadth_daily` cache (lives in `stock_system`)
- Automated cron / systemd setup (manual trigger in v1)
- amount / suspended / limit_up columns (computed at query time)
