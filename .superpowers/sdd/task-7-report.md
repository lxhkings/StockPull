# Task 7 Report: CN price/weekly/etf/index → ts_ingest

## Status
**PASS**

## Commit
- **Hash:** `b23ba9912ec88053c4b8deb56a252d836e9f8ee9` (short: `b23ba99`)
- **Branch:** `feature/api-centric-modularization`
- **Message:** `refactor: CN 日线/周线/ETF/指数归位 ts_ingest`

## Moves

| Old path | New path |
|----------|----------|
| `data/stock_updater_cn_tushare.py` | `ts_ingest/prices_cn.py` |
| `data/stock_updater_cn_weekly.py` | `ts_ingest/prices_cn_weekly.py` |
| `data/etf_updater_cn.py` | `ts_ingest/etf_cn.py` |
| `data/index_updater_cn.py` | `ts_ingest/index_cn.py` |

## Import remaps

| Old | New |
|-----|-----|
| `data.stock_updater_cn_tushare` | `ts_ingest.prices_cn` |
| `data.stock_updater_cn_weekly` | `ts_ingest.prices_cn_weekly` |
| `data.etf_updater_cn` | `ts_ingest.etf_cn` |
| `data.index_updater_cn` | `ts_ingest.index_cn` |

### Call sites updated
- `data/market_cn.py` — prices / weekly / etf imports
- `main.py` — rebase ETF import
- Tests: `test_etf_updater_cn`, `test_index_updater_cn`, `test_stock_updater_cn_weekly`, `test_cn_index_price`, `test_market_cn_etf_hook`, `test_cli_rebase_etf`
- Comment touch: `data/index_base.py`, header in `ts_ingest/prices_cn_weekly.py`

### Internal imports in moved files
- Already used `ts_ingest.client` / `core.*` / `modules.*` / `data.index_base` — no broken cross-refs after move.
- `index_cn.py` still depends on `data.index_base` (shared helper; US/HK index updaters remain in `data/`).

## Verification

```bash
rg -n "stock_updater_cn_tushare|stock_updater_cn_weekly|etf_updater_cn|index_updater_cn" -g'*.py' --glob '!**/.venv/**' --glob '!docs/**'
# no hits

uv run pytest tests/ -q
============================= 397 passed in 2.82s ==============================
```

| Metric | Value |
|--------|-------|
| Collected | 397 |
| Passed | 397 |
| Failed | 0 |
| Skipped | 0 |

## Concerns
- Test **filenames** still use old names (`test_etf_updater_cn.py`, `test_index_updater_cn.py`, `test_stock_updater_cn_weekly.py`); only import paths were remapped. Optional follow-up rename.
- **README.md / CLAUDE.md** still document old `data/stock_updater_cn_*` / `index_updater_cn` paths (docs excluded from rg gate; Task 9 may rename package + refresh docs).
- Package remains `ts_ingest` until Task 9 rename.
- `index_cn.update_csi800()` (constituent snapshot) is still not wired from `market_cn.update_index()` (pre-existing: CN index list is full A-share via `backfill_stocks_a`; only price path uses CSI800). No behavior change in this task.
