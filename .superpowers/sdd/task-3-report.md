# Task 3 Report: C1 trading_calendar

## Status
**PASS**

## Commit
- **Hash:** `7927bc041d0323398ec914601e34e9dc45199a51` (short: `7927bc0`)
- **Branch:** `feature/api-centric-modularization`
- **Message:** `feat: 抽取 core.trading_calendar（US/CN 交易日）`
- **Files (7):**
  - `core/trading_calendar.py` (new)
  - `tests/test_trading_calendar.py` (new)
  - `data/stock_updater_us.py`
  - `data/stock_updater_cn_tushare.py`
  - `data/stock_updater_cn_weekly.py`
  - `data/market_us.py`
  - `tests/test_stock_updater_cn_weekly.py`

## Changes

| Item | Action |
|------|--------|
| `core/trading_calendar.py` | New pure helpers: `last_us_trading_date(now=None)`, `last_cn_trading_date(now=None)` |
| `tests/test_trading_calendar.py` | 8 unit tests (US Sat/Sun/Mon-before-5 / weekday; CN before/after 16, weekend, Mon) |
| `data/stock_updater_us.py` | Delete `_last_us_trading_date`; import/call `last_us_trading_date` |
| `data/stock_updater_cn_tushare.py` | Delete `_last_cn_trading_date`; import/call `last_cn_trading_date` |
| `data/stock_updater_cn_weekly.py` | Import from `core.trading_calendar` (was private import from tushare updater) |
| `data/market_us.py` | Call `last_us_trading_date` (was `stock_updater_us._last_us_trading_date`) |
| `tests/test_stock_updater_cn_weekly.py` | Patch path → `last_cn_trading_date` (no underscore) |

## Call-site verification
```
rg -n "_last_us_trading_date|_last_cn_trading_date" -g'*.py' --glob '!**/.venv/**'
# no hits
```

## Test Summary
```
uv run pytest tests/ -q
============================= 388 passed in 2.24s ==============================
```
- Collected: 388 (was 380; +8 from `test_trading_calendar.py`)
- Passed: 388
- Failed: 0

## Behavior notes
- Logic copied from private helpers; only additive change is optional `now: datetime | None = None` for deterministic tests.
- Default path (`now is None` → `datetime.now()`) preserves production behavior.
- No schema changes, no performance changes.

## Concerns
None material.
- US helper still treats Mon 05:00+ and Tue–Fri the same as “yesterday” (both branches return prev day) — pre-existing behavior, intentionally preserved.
- No HK trading-date helper yet; out of scope for C1.
