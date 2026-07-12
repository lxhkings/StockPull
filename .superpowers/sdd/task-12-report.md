# Task 12 Report: jobs 编排层（pipeline + market_*）

## Status
**PASS**

## Commit
- **Hash:** `14b4d16bb78f0d21ca9f8e624a578b6461d20c0e` (short: `14b4d16`)
- **Branch:** `feature/api-centric-modularization`
- **Message:** `refactor: pipeline 与 market_* 迁入 jobs/`

## Moves (shell only)

| Action | Path |
|--------|------|
| `git mv` | `data/pipeline.py` → `jobs/pipeline.py` |
| `git mv` | `data/market_us.py` → `jobs/market_us.py` |
| `git mv` | `data/market_cn.py` → `jobs/market_cn.py` |
| `git mv` | `data/market_hk.py` → `jobs/market_hk.py` |

**Pre-existing:** `jobs/__init__.py` (empty package marker from earlier task).

**Left in `data/`:** only `data/__init__.py` (+ `__pycache__`) — emptied by Task 13.

## Import remaps

| Old | New |
|-----|-----|
| `data.pipeline` | `jobs.pipeline` |
| `data.market_us` | `jobs.market_us` |
| `data.market_cn` | `jobs.market_cn` |
| `data.market_hk` | `jobs.market_hk` |
| `from data import market_*` | `from jobs import market_*` |

### Call sites updated

| File | Change |
|------|--------|
| `main.py` | `from jobs.pipeline import Pipeline`; `_import_market` → `from jobs import market_{us,cn,hk}` |
| `apis/yfinance/prices_intraday.py` | lazy `from jobs.market_us import list_active_tickers` |
| `tests/test_pipeline.py` | `jobs.pipeline` |
| `tests/test_pipeline_intraday.py` | `jobs.pipeline` |
| `tests/test_market_cn.py` | `jobs.market_cn` (+ patches) |
| `tests/test_market_cn_etf_hook.py` | `jobs.market_cn` |
| `tests/test_market_hk.py` | `jobs.market_hk` (+ mock fix, see below) |
| `tests/test_market_us_intraday.py` | `from jobs import market_us` |
| `tests/test_cn_index_price.py` | `jobs.market_cn` |
| `tests/test_us_index_price.py` | `jobs.market_us` |
| `tests/test_intraday_updater_us.py` | patch `jobs.market_us.list_active_tickers` |

`main.py` already imported `apis.tushare.etf_cn` / `apis.yfinance.prices_intraday` / `apis.tushare.orchestrator` / `apis.futu.orchestrator` from prior P3 tasks — no further change needed there.

## Boundary check

```bash
rg -n "import yfinance|import tushare|from futu|import futu" jobs/
# expect: no hits → OK

rg -n "data\.(pipeline|market_us|market_cn|market_hk)|from data import market" -g'*.py' --glob '!**/.venv/**' --glob '!docs/**'
# expect: no hits → OK
```

`jobs/*` imports only: `apis.*`, `core.*`, `modules.*`, stdlib (`logging`, `typing`, `datetime`, `pandas`).

## Test fix (related)

`tests/test_market_hk.py::test_update_index_delegates_to_hsi` previously patched `get_conn` / `query` on the market module, but `update_index()` calls `get_index_tickers` (from `modules.db_admin`). That latent bad mock only failed when NAS was unreachable (real DB connect). Fixed to side-effect-mock `jobs.market_hk.get_index_tickers` (prev/curr sets) — no production logic change.

## Verification

```bash
uv run pytest tests/ -q
======================== 394 passed, 3 skipped in 4.10s ========================
```

| Metric | Value |
|--------|-------|
| Collected | 397 |
| Passed | 394 |
| Failed | 0 |
| Skipped | 3 (`test_db_smoke`) |

## Concerns
- **Layering inversion:** `apis/yfinance/prices_intraday.py` still lazy-imports `jobs.market_us.list_active_tickers` (was `data.market_us`). Violates intended `jobs → apis` one-way rule; works via lazy import but should later inject tickers / use `modules.db_admin.get_index_tickers` so apis never touch jobs.
- **Docs stale:** `Claude.md` / `README.md` still describe `data/pipeline.py` / `data/market_*.py` (P4 / Task 14).
- **`data/` not removed:** only `__init__.py` remains — Task 13.
- **Unused imports in `jobs/market_hk.py`:** `get_conn`, `query` unused after index path moved to `get_index_tickers` — pre-existing; not cleaned (surgical move).
- No business logic / rate-limit / CLI behavior changes; pure path relocation + import rewrite + one broken mock fix.
