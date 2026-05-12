# Project_B — Unified Stocks Ingest

Daily-K ingest for US (yfinance) + A-share (akshare/efinance) + HK (akshare/efinance), writing into shared NAS MariaDB.

See `docs/superpowers/plans/` for the implementation plan.

## Requirements

- Python 3.12+ (`.python-version` 指定 3.12)
- MariaDB on NAS (192.168.8.9:3306)
- uv (Python 包管理器)

## Quick start

```bash
# 使用 uv 管理 Python 版本和依赖
uv venv --python 3.12
source .venv/bin/activate
cp .env.example .env  # fill DB_PASSWORD

uv run main.py init      # one-time: insert CSI800/HSI rows into indices table
uv run main.py daily     # run all markets
```

## CLI

```bash
uv run main.py daily --market us   # US market incremental
uv run main.py daily --market cn   # CN market incremental
uv run main.py daily --market hk   # HK market incremental
uv run main.py daily               # all markets (default)

uv run main.py init                # one-time index metadata seed
uv run main.py rebase --market cn  # full hfq re-pull from START_DATE
uv run main.py status              # DB sync summary

# Tushare 一次性回填（独立子系统）
uv run main.py tushare-backfill --dry-run                       # 预检 + 预算估算
uv run main.py tushare-backfill --scope lists                   # 仅列表
uv run main.py tushare-backfill --scope prices --market hk      # 仅 HK 日 K
uv run main.py tushare-backfill                                  # 全量（约 30–60 分钟）
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
# 北京时间每日 18:00 运行（美股收盘后）
0 18 * * 1-5 /path/to/project/scripts/daily_update.sh >> /var/log/stocks.log 2>&1
```

**北京时间美股收盘说明：**

美股收盘时间为北京时间凌晨 5:00。程序自动计算最近已收盘的交易日：
- 周一凌晨 5:00 前 → 回补上周五数据
- 周一凌晨 5:00 后 → 回补上周五数据（等待周一收盘）
- 周六/周日 → 回补周五数据
- 周二至周五凌晨 5:00 前 → 回补前一天数据
- 周二至周五凌晨 5:00 后 → 回补前一天数据（等待当天收盘）

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
| TUSHARE_TOKEN | (optional) | Tushare API token for backfill |

History depths are configured in `config.py`:
- US: 5 years
- CN/HK: 15 years (from 2010-01-01)

## Tests

```bash
uv run pytest tests/ -v
```

44 tests covering ticker utils, config, DB smoke, pipeline, index updaters,
stock updaters, market modules, reconciliation, and CLI.
