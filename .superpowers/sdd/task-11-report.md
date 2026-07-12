# Task 11 Report: static 成分股源适配迁入 apis.static

## Status
**PASS**

## Commit
- **Hash:** `7d322bdf327d41c1f379c3052c304b5b568d3dca` (short: `7d322bd`)
- **Branch:** `feature/api-centric-modularization`
- **Message:** `refactor: 成分股源适配迁入 apis.static（写表仍 modules.index_base）`

## Moves (shell only)

| Action | Path |
|--------|------|
| `mkdir -p` | `apis/static` |
| `git mv` | `data/index_updater_us.py` → `apis/static/sp500_github.py` |
| `git mv` | `data/index_updater_russell1000.py` → `apis/static/russell_ishares.py` |
| `git mv` | `data/index_updater_hk.py` → `apis/static/hsi_csv.py` |
| `git mv` | `data/hsi_constituents.csv` → `apis/static/hsi_constituents.csv` |
| `touch` | `apis/static/__init__.py` |

**NOT moved:** `modules/index_base.py` (already in modules/; write-table helpers stay there).

## Fixes

| File | Change |
|------|--------|
| `apis/static/hsi_csv.py` | CSV path → `Path(__file__).with_name("hsi_constituents.csv")`; drop `os` |
| `apis/static/sp500_github.py` | Module docstring only (new package name) |
| All three static adapters | Keep `from modules.index_base import …` (already correct) |

## Import remaps

| Old | New |
|-----|-----|
| `data.index_updater_us` | `apis.static.sp500_github` |
| `data.index_updater_russell1000` | `apis.static.russell_ishares` |
| `data.index_updater_hk` | `apis.static.hsi_csv` |

Call sites:

| File | Import / call |
|------|----------------|
| `data/market_us.py` | `from apis.static import sp500_github` / `russell_ishares` → `.update_sp500()` / `.update_russell1000()` |
| `data/market_hk.py` | `from apis.static import hsi_csv` → `.update_hsi()` |
| `tests/test_index_updater_hk.py` | `from apis.static.hsi_csv import _fetch_hsi` |
| `tests/test_index_updater_russell1000.py` | all patches/imports → `apis.static.russell_ishares` |
| `tests/test_market_hk.py` | `@patch("data.market_hk.hsi_csv")` |

## Verification

```bash
rg -n "index_updater_us|index_updater_hk|index_updater_russell|data\.index_updater" -g'*.py' --glob '!**/.venv/**' --glob '!docs/**'
# expect: comment-only (test filename header; backfill_lists docstring) → OK

rg -n "from apis\.static|import apis\.static" apis/tushare/ || true
# expect no hits → none

uv run pytest tests/ -q
============================= 397 passed in 2.89s ==============================
```

| Metric | Value |
|--------|-------|
| Collected | 397 |
| Passed | 397 |
| Failed | 0 |
| Skipped | 0 |

Boundary: `apis.tushare` does **not** import `apis.static`. Static adapters write via `modules.index_base` only.

## Concerns
- **Docs stale:** `Claude.md` / `README.md` still list `data/index_updater_*.py` and `data/hsi_constituents.csv` (scoped to code move; docs update is P4 / later task).
- **Comment-only refs:** `apis/tushare/backfill_lists.py` still mentions `index_updater_us.py` in prose — not import-breaking.
- **Test file names:** `tests/test_index_updater_hk.py`, `tests/test_index_updater_russell1000.py` still use old module names; not renamed (out of pure-move scope). No dedicated `test_sp500_github` yet (none existed for `index_updater_us` either).
- **Cache path drift:** `russell_ishares._CACHE_FILE` is now under `apis/static/.cache/` (was `data/.cache/`) via `Path(__file__).parent` — behaviorally fine; any pre-existing `data/.cache/iwb_accession.json` is orphaned, not migrated.
- No logic changes; pure path relocation + import rewrite + HSI CSV path fix.
