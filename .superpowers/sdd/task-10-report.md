# Task 10 Report: yfinance 适配器迁入 apis.yfinance

## Status
**PASS**

## Commit
- **Hash:** `1a2807d65eaf4eb36287f09340dd10d3448298c0` (short: `1a2807d`)
- **Branch:** `feature/api-centric-modularization`
- **Message:** `refactor: yfinance 适配器迁入 apis.yfinance`

## Moves (shell only)

| Action | Path |
|--------|------|
| `mkdir -p` | `apis/yfinance` |
| `git mv` | `data/yf_client.py` → `apis/yfinance/client.py` |
| `git mv` | `data/stock_updater_us.py` → `apis/yfinance/prices_us.py` |
| `git mv` | `data/stock_updater_hk.py` → `apis/yfinance/prices_hk.py` |
| `git mv` | `data/stock_updater_us_weekly.py` → `apis/yfinance/prices_us_weekly.py` |
| `git mv` | `data/intraday_updater_us.py` → `apis/yfinance/prices_intraday.py` |
| `git mv` | `data/ticker_utils.py` → `apis/yfinance/ticker_utils.py` |
| `touch` | `apis/yfinance/__init__.py` |

## Import remaps

| Old | New |
|-----|-----|
| `data.yf_client` | `apis.yfinance.client` |
| `data.stock_updater_us` | `apis.yfinance.prices_us` |
| `data.stock_updater_hk` | `apis.yfinance.prices_hk` |
| `data.stock_updater_us_weekly` | `apis.yfinance.prices_us_weekly` |
| `data.intraday_updater_us` | `apis.yfinance.prices_intraday` |
| `data.ticker_utils` | `apis.yfinance.ticker_utils` |

Package-style call sites in market adapters kept local aliases to minimize churn:

| File | Import |
|------|--------|
| `data/market_us.py` | `from apis.yfinance import prices_us as stock_updater_us` |
| `data/market_us.py` | `from apis.yfinance import prices_us_weekly as stock_updater_us_weekly` (lazy) |
| `data/market_us.py` | `from apis.yfinance.client import download_with_retry` |
| `data/market_us.py` | `from apis.yfinance.prices_intraday import update_intraday` (lazy) |
| `data/market_hk.py` | `from apis.yfinance import prices_hk as stock_updater_hk` |
| `main.py` | `from apis.yfinance.prices_intraday import update_intraday, SUPPORTED_INTERVALS` |

Internal imports among moved modules: `from apis.yfinance.client import …`.  
`prices_intraday` still imports `data.market_us.list_active_tickers` (market layer stays in `data/`).

Tests/patches updated: `test_yf_client`, `test_intraday_updater_us`, `test_stock_updater_us_weekly`, `test_ticker_utils`, `test_market_us_intraday`.  
`test_market_hk` still patches `data.market_hk.stock_updater_hk` (alias preserved).

## Verification

```bash
rg -n "data\.yf_client|data\.stock_updater_us|data\.stock_updater_hk|data\.intraday_updater|data\.ticker_utils" -g'*.py' --glob '!**/.venv/**' --glob '!docs/**'
# expect no hits → none

uv run pytest tests/ -q
============================= 397 passed in 3.12s ==============================
```

| Metric | Value |
|--------|-------|
| Collected | 397 |
| Passed | 397 |
| Failed | 0 |
| Skipped | 0 |

## Concerns
- **Docs stale:** `Claude.md` / `README.md` still reference `data/yf_client.py`, `data/ticker_utils.py`, `data/stock_updater_us_weekly.py`, `data/intraday_updater_us.py` (scoped to `.py` only; docs not bulk-updated).
- **Comment-only refs:** `core/batch_utils.py`, `core/retry_utils.py`, `apis/tushare/prices_cn.py`, `apis/tushare/backfill_lists.py` still mention old filenames in prose — not import-breaking.
- **Alias indirection:** `market_us` / `market_hk` bind new modules under old local names (`stock_updater_us` / `stock_updater_hk`) so existing attribute patches keep working; a later cleanup can drop aliases and rename call sites.
- **Test file names:** `tests/test_yf_client.py`, `tests/test_stock_updater_us_weekly.py`, `tests/test_intraday_updater_us.py` still use old module names; not renamed (out of pure-move scope).
- No logic changes; pure path relocation + import rewrite.
