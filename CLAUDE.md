# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Setup
uv venv --python 3.12
source .venv/bin/activate
cp .env.example .env  # fill DB_PASSWORD, TUSHARE_TOKEN

# Run tests
uv run pytest tests/ -v                    # all tests
uv run pytest tests/test_index_updater_cn.py -v  # single file
uv run pytest tests/test_cn_index_price.py::test_update_index_price_uses_tushare_index_daily  # single test

# CLI
uv run main.py init                 # one-time: seed index metadata
uv run main.py daily                # all markets
uv run main.py daily --market us
uv run main.py daily --market cn    # single market
uv run main.py daily --market cn --code 600519.SH  # single ticker (debug)
uv run main.py rebase --market cn   # full hfq re-pull
uv run main.py status               # DB sync summary

# Tushare 回填（股票基础信息、行业分类）
uv run main.py tushare-backfill --scope lists --market cn  # A股基础信息+行业

# Cron
./scripts/daily_update.sh [us|cn|hk|all]
```

## Architecture

Three-market daily-K ingest (US/CN/HK) into shared MariaDB on Synology NAS (192.168.8.9:3306).

**Pipeline flow** (`data/pipeline.py`):
1. `update_index()` — snapshot index constituents, detect added/removed
2. `backfill_new()` — full history for new tickers
3. `incremental()` — resume from sync_log for existing tickers
4. `update_index_price()` — index daily close

**Market modules** follow `MarketModule` protocol (defined in `data/pipeline.py`):
- `data/market_us.py` — yfinance, SP500 from GitHub CSV
- `data/market_cn.py` — tushare (CSI800 constituents, index prices, stock basic), yfinance (stock prices hfq)
- `data/market_hk.py` — yfinance, HSI from local CSV (`data/hsi_constituents.csv`)

**CN Market 数据源：**
- CSI800 成分股: tushare `index_weight` API → stocks 表 join 获取 name/gics_sector
- CSI800 指数价格: tushare `index_daily` API
- A股基础信息: tushare `stock_basic` API（含行业分类 `industry` 字段）
- A股日线价格: tushare `pro_bar` API (hfq)

**HK Market 数据源：**
- HSI 成分股: 本地 CSV `data/hsi_constituents.csv`（手动维护）
- 港股日线价格: yfinance

**Key patterns:**
- CN/HK prices are hfq (后复权/post-adjusted); US prices are raw
- `ON DUPLICATE KEY UPDATE` for stocks table (更新 name 和 gics_sector)
- `INSERT IGNORE` for index_constituents (daily snapshots)
- `sync_log` table tracks per-ticker last successful sync date
- `index_constituents` table stores daily snapshots with `snapshot_date`
- `constituent_changes` table tracks ADDED/REMOVED diffs
- `gics_sector` column in stocks table filled by tushare `stock_basic.industry`

**Ticker formats** (`data/ticker_utils.py`):
- Canonical: `600519.SH`, `00700.HK`, `AAPL`
- tushare/akshare A-share: `600519.SH` (与 canonical 一致)
- akshare HK: 5-digit with leading zeros (`00700`)
- efinance: same as akshare

## Configuration

Secrets in `.env` (see `.env.example`). `DB_PASSWORD` and `TUSHARE_TOKEN` are required.

History depths in `config.py`: US=5yr, CN/HK=15yr from 2010-01-01.

Retry/delay settings in `config.py`: `AKSHARE_RETRY_COUNT=5`, `AKSHARE_RETRY_DELAY=3.0`, `AKSHARE_REQUEST_DELAY=1.5`.

Tushare rate limiting in `config.py`: `TUSHARE_RATE_INTERVAL=0.12` (每分钟最多 500 次).

## Network Notes

The codebase clears proxy environment variables in `main.py` (sets `NO_PROXY=*`) to avoid macOS system proxy interference with akshare/efinance HTTP requests to eastmoney.com APIs.

## Database

MariaDB on Synology NAS. `db.py` sets `time_zone='+08:00'` on each connection.

Tables: `stocks`, `prices`, `indices`, `index_constituents`, `constituent_changes`, `index_prices`, `index_sync_log`, `sync_log`.

**stocks 表字段:**
- `ticker` — 主键（canonical format）
- `name` — 股票名称
- `gics_sector` — 行业分类（tushare `stock_basic.industry`）
- `exchange` — 交易所（SH/SZ/BJ/HK/US）