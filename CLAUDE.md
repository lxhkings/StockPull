# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Setup
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # fill DB_PASSWORD

# Run tests
pytest tests/ -v                    # all tests
pytest tests/test_ticker_utils.py   # single file
pytest tests/test_reconcile.py::test_both_sources_agree_uses_primary  # single test

# CLI
python main.py init                 # one-time: seed index metadata
python main.py daily                # all markets
python main.py daily --market cn    # single market
python main.py daily --market cn --code 600519.SH  # single ticker (debug)
python main.py rebase --market cn   # full hfq re-pull
python main.py status               # DB sync summary

# Tushare 一次性回填（独立子系统）
python main.py tushare-backfill --dry-run                       # 预检 + 预算估算
python main.py tushare-backfill --scope lists                   # 仅列表
python main.py tushare-backfill --scope prices --market hk      # 仅 HK 日 K
python main.py tushare-backfill                                  # 全量（约 30–60 分钟）

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
- `data/market_cn.py` — akshare + efinance, CSI800 from csindex.com.cn
- `data/market_hk.py` — akshare, HSI from sina

**Key patterns:**
- CN/HK prices are hfq (后复权/post-adjusted); US prices are raw
- Two-source reconciliation (`data/reconcile.py`) during backfill: akshare primary, efinance secondary, tolerance 0.5%
- `ON DUPLICATE KEY UPDATE` for rebase overwrites; `INSERT IGNORE` for US legacy
- `sync_log` table tracks per-ticker last successful sync date
- `index_constituents` table stores daily snapshots with `snapshot_date`
- `constituent_changes` table tracks ADDED/REMOVED diffs

**Ticker formats** (`data/ticker_utils.py`):
- Canonical: `600519.SH`, `00700.HK`, `AAPL`
- akshare A-share: 6-digit code only (`600519`)
- akshare HK: 5-digit with leading zeros (`00700`)
- efinance: same as akshare

## Configuration

Secrets in `.env` (see `.env.example`). `DB_PASSWORD` is required (raises KeyError).

History depths in `config.py`: US=5yr, CN/HK=15yr from 2010-01-01.

Retry/delay settings in `config.py`: `AKSHARE_RETRY_COUNT=5`, `AKSHARE_RETRY_DELAY=3.0`, `AKSHARE_REQUEST_DELAY=1.5`.

## Network Notes

The codebase clears proxy environment variables in `main.py` (sets `NO_PROXY=*`) to avoid macOS system proxy interference with akshare/efinance HTTP requests to eastmoney.com APIs.

## Database

MariaDB on Synology NAS. `db.py` sets `time_zone='+08:00'` on each connection.

Tables: `stocks`, `prices`, `indices`, `index_constituents`, `constituent_changes`, `index_prices`, `index_sync_log`, `sync_log`.
