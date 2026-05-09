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

## CLI

```bash
python main.py daily [us|cn|hk|all]   # daily incremental (default: all)
python main.py init                     # one-time index metadata seed
python main.py rebase [us|cn|hk|all]   # full hfq re-pull from START_DATE
python main.py status                   # DB sync summary
```

## Architecture

```
main.py
  └── data/pipeline.py        # generic Pipeline orchestrator
        ├── data/market_us.py  # US adapter (yfinance)
        ├── data/market_cn.py  # CN adapter (akshare + efinance)
        └── data/market_hk.py  # HK adapter (akshare)

data/index_updater_*.py        # per-market constituent snapshots
data/stock_updater_*.py        # per-market daily-K fetchers
data/reconcile.py              # two-source price comparison
data/ticker_utils.py           # canonical ticker format conversions
db.py                          # connection pool + sync_log helpers
config.py                      # env-driven configuration
```

Each market module exposes the `MarketModule` protocol:
- `update_index()` — snapshot constituents, detect changes
- `list_active_tickers()` — current universe
- `backfill_new(tickers)` — full history for new additions
- `incremental(tickers)` — resume from sync_log
- `update_index_price()` — index ETF daily close
- `rebase(tickers)` — full re-pull for hfq drift

## Data sources

| Market | Index | Stock prices | Index price |
|--------|-------|-------------|-------------|
| US     | GitHub CSV (SP500) | yfinance | ^GSPC via yfinance |
| CN     | csindex.com.cn (CSI800) | akshare hfq + efinance | 510800 ETF via akshare |
| HK     | sina (HSI) | akshare hfq | 2800.HK via akshare |

## Reconciliation

`data/reconcile.py` compares close prices from two sources with a configurable
tolerance (default 0.5%). Used during backfill to cross-validate akshare vs
efinance for A-share data.

## Cron setup

```bash
# Daily at 18:00 CST (after market close)
0 18 * * 1-5 /path/to/project/scripts/daily_update.sh >> /var/log/stocks.log 2>&1
```

Logs are written to `logs/daily_YYYY-MM-DD.log`.

## Configuration

All secrets live in `.env` (see `.env.example`):

| Variable | Default | Description |
|----------|---------|-------------|
| DB_HOST | 192.168.8.9 | MariaDB host |
| DB_PORT | 3306 | MariaDB port |
| DB_USER | root | MariaDB user |
| DB_PASSWORD | (required) | MariaDB password |
| DB_NAME | stocks | Database name |

History depths are configured in `config.py`:
- US: 5 years
- CN/HK: 15 years (from 2010-01-01)

## Tests

```bash
pytest tests/ -v
```

44 tests covering ticker utils, config, DB smoke, pipeline, index updaters,
stock updaters, market modules, reconciliation, and CLI.
