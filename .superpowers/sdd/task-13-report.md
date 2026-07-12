# Task 13 Report: 移除已搬空的 data 包

## Status
**PASS**

## Pre-fix (dependency inversion)

`apis/yfinance/prices_intraday.py` 曾 lazy-import `jobs.market_us.list_active_tickers`，违反 `apis → jobs` 禁止方向。

| Item | Change |
|------|--------|
| Production | `from modules.db_admin import get_index_tickers`；宇宙 = `sorted(set(SP500) \| set(RUSSELL1000))`（对齐 `list_active_tickers(None)`） |
| Tests | `tests/test_intraday_updater_us.py` patch 改为 `apis.yfinance.prices_intraday.get_index_tickers` |
| Verify | `rg -n "from jobs\|import jobs" apis/` → 无命中 |

**Commit:** `9fc2ce71c6829a3db1619fbc35e3bf6e467f17f6` (short: `9fc2ce7`)  
**Message:** `fix: prices_intraday 不再依赖 jobs（用 modules.db_admin）`

## Task 13 body

```bash
find data -type f ! -path '*/__pycache__/*'
# → only data/__init__.py (+ untracked .DS_Store / .cache)
git rm -r data/
```

| Action | Result |
|--------|--------|
| Tracked | `data/__init__.py` deleted |
| Untracked local junk | `.DS_Store` / `.cache` removed with `rm -rf data/` |
| Package | `data/` no longer exists |

**Commit:** `65061010ce4631052b2406cc7b9878ed24b8dd44` (short: `6506101`)  
**Message:** `chore: 移除已搬空的 data 包`

## Verification

```bash
uv run pytest tests/ -q
======================== 394 passed, 3 skipped in 4.28s ========================
```

| Metric | Value |
|--------|-------|
| Collected | 397 |
| Passed | 394 |
| Failed | 0 |
| Skipped | 3 (`test_db_smoke`) |

## Concerns
- None for this task. Docs still pointed at `data/` until Task 14.
