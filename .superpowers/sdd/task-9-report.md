# Task 9 Report: futu_ingest→apis.futu, ts_ingest→apis.tushare

## Status
**PASS**

## Commit
- **Hash:** `1a89b5a896ff87a11a0ce39adda540bd41028e80` (short: `1a89b5a`)
- **Branch:** `feature/api-centric-modularization`
- **Message:** `refactor: futu_ingest→apis.futu, ts_ingest→apis.tushare`

## Moves (shell only)

| Action | Path |
|--------|------|
| `mkdir -p` | `apis/yfinance`, `apis/static` |
| `touch` | `apis/__init__.py` |
| `git mv` | `futu_ingest` → `apis/futu` |
| `git mv` | `ts_ingest` → `apis/tushare` |
| `mkdir -p` + `touch` | `jobs/__init__.py` |

**Not moved (Task 10):** yfinance / `data/` market files.

## Import remaps

| Old | New |
|-----|-----|
| `futu_ingest` | `apis.futu` |
| `from futu_ingest ...` | `from apis.futu ...` |
| `ts_ingest` | `apis.tushare` |
| `from ts_ingest ...` | `from apis.tushare ...` |
| `patch("futu_ingest....")` | `patch("apis.futu....")` |
| `patch("ts_ingest....")` | `patch("apis.tushare....")` |

Package-internal absolute imports under `apis/futu` and `apis/tushare` updated the same way. Call sites: `main.py`, `data/market_cn.py`, `scripts/verify_cn_etfs.py`, comments in `core/*` / `modules/index_base.py` / `data/yf_client.py`, and all related `tests/test_*.py`.

## Verification

```bash
rg -n "futu_ingest|ts_ingest" -g'*.py' --glob '!**/.venv/**' --glob '!docs/**'
# expect no hits → none

uv run pytest tests/ -q
============================= 397 passed in 4.04s ==============================
```

| Metric | Value |
|--------|-------|
| Collected | 397 |
| Passed | 397 |
| Failed | 0 |
| Skipped | 0 |

Import smoke: `from apis.futu import orchestrator` / `from apis.tushare import orchestrator` OK after `uv pip install -e .`.

## Concerns
- **Docs stale:** `CLAUDE.md` / `README.md` still document `futu_ingest/` and `ts_ingest/` paths (Task 9 scoped to `.py`; docs not bulk-updated).
- **Empty placeholder dirs:** `apis/yfinance/` and `apis/static/` exist on disk but are empty (no `.gitkeep`); git does not track them until Task 10 adds files.
- **egg-info / editable install:** `stockpull.egg-info/top_level.txt` may still list old top-level names until reinstall; setuptools `packages.find` picks up `apis` / `jobs` automatically. Re-run `uv pip install -e .` if imports fail in a fresh env.
- **Git rename noise:** empty `__init__.py` files caused rename detector to pair parent packages oddly in the commit summary; on-disk content is correct (all three package inits empty as before).
- No logic changes; pure path relocation + import rewrite.
