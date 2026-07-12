# Task 5 Report: C3 modules/price_write

## Status
**PASS**

## Commit
- **Hash:** `74cbf2ef141c0b431a7501f1d5a4c326155879a5` (short: `74cbf2e`)
- **Branch:** `feature/api-centric-modularization`
- **Message:** `feat: modules.price_write 统一 prices+sync 批提交`
- **Files (6):**
  - `modules/price_write.py` (new)
  - `tests/test_price_write.py` (new)
  - `data/stock_updater_cn_tushare.py`
  - `data/stock_updater_cn_weekly.py`
  - `data/stock_updater_us.py`
  - `data/stock_updater_hk.py`

## Changes

| Item | Action |
|------|--------|
| `modules/price_write.py` | Add `flush_prices_and_sync(conn, price_rows, sync_rows, *, on_duplicate=True, price_table="prices")` — prices then sync_log, single commit; empty both → return |
| `tests/test_price_write.py` | on_duplicate SQL, INSERT IGNORE SQL, empty noop, sync-only one commit, prices_weekly table |
| `data/stock_updater_cn_tushare.py` | `_flush_batch` → thin wrapper; drop local `_save_prices_batch` |
| `data/stock_updater_cn_weekly.py` | `_flush_batch` → `flush_prices_and_sync(..., price_table="prices_weekly")`; keep `_save_weekly_prices_batch` for unit test table assertion |
| `data/stock_updater_us.py` | `_download_and_save` accumulates successful price/sync rows → one `flush_prices_and_sync(..., on_duplicate=False)`; per-ticker failures still `set_sync_error` |
| `data/stock_updater_hk.py` | Per-ticker success: one flush (ON DUPLICATE); errors still `set_sync_error` |

## SQL semantics
| Mode | prices SQL | Markets |
|------|------------|---------|
| `on_duplicate=True` | `INSERT ... ON DUPLICATE KEY UPDATE open/high/low/close/volume=VALUES(...)` | CN daily, CN weekly (`prices_weekly`), HK |
| `on_duplicate=False` | `INSERT IGNORE INTO prices ...` | US daily |

sync_log SQL unchanged (same as prior `_flush_batch` / `_upsert_sync_log`):
- `last_date = IF(VALUES(status)='ok', VALUES(last_date), last_date)`

## Empty buffers
Both `price_rows` and `sync_rows` empty → return without cursor/commit (no error).

## Call-site notes
- CN daily/weekly: keep `_flush_batch` as thin wrapper so existing patches/tests still work.
- US: one flush per yfinance batch after successful tickers buffered; write failure marks those ok_tickers via `set_sync_error`.
- HK: serial fetch unchanged; prices+sync now single commit per successful ticker (was 2 commits: `_save_prices` + `set_sync_ok`).
- Rate limits / download paths untouched.
- US weekly / ETF updaters not in this task scope.

## Extension beyond minimal signature
- Optional `price_table: str = "prices"` (whitelist: `prices`, `prices_weekly`) so CN weekly keeps writing `prices_weekly` while reusing the same flush helper.

## Test Summary
```
uv run pytest tests/ -q
============================= 397 passed in 3.66s ==============================
```
- Collected: 397 (was 392; +5 from `test_price_write`)
- Passed: 397
- Failed: 0
- Skipped: 0 (NAS reachable this run; earlier flake on `test_market_hk` was env DB, not this change)

Also verified: `tests/test_stock_updater_cn_weekly.py` all green.

## Concerns
- US batch write failure now fails the whole successful buffer (not per-ticker mid-write); recovery marks all buffered ok tickers as error. Preferable to N commits; rare path.
- `price_table` is f-string into SQL with whitelist only — do not pass untrusted table names.
- CN weekly retains `_save_weekly_prices_batch` solely for existing unit test; runtime flush path no longer calls it.
- First full-suite run once hit real NAS via `test_market_hk` flake; re-run green — unrelated to price_write.
