# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

**项目架构与结构见 README.md。**

**行为准则见全局 CLAUDE.md（~/.claude/CLAUDE.md）。**

---

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

# Futu 美股基本面
uv run main.py futu-full             # 全量采集（首次/重建）
uv run main.py futu-full --scope financial
uv run main.py futu-sync            # 增量（cron 每日；按接口频率节流）
uv run main.py futu-sync --scope daily
uv run main.py futu-flush           # 兜底：把本地缓冲重放到 NAS（futu-full/sync flush 失败后）

# futu-full/futu-sync 先写本地缓冲（.futu_buffer/pending.sqlite），收尾自动 flush 到 NAS。
# NAS 中途宕机不丢数据；flush 失败时跑 futu-flush 兜底。

# Tushare 回填（股票基础信息、行业分类、财务、估值、股东回报）
uv run main.py tushare-sync --scope lists --market cn  # 增量/日常用（=tushare-backfill 不带--start）
uv run main.py tushare-full --scope valuation           # 全量强制回填（=tushare-backfill --start 2010起）
uv run main.py tushare-backfill --scope valuation --start 20200101  # 自定义起点才用这个
# tushare-*: 手动一次性回填工具，不在 daily cron 里；本地缓冲同 futu，flush 失败跑 tushare-flush 兜底

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

## 扩展新功能前必读（强制）

新增/修改功能前，先判断属于哪个模块家族，MUST 遵循该家族既有模式，不允许绕过或新建平行结构。

**跨家族共享层（`core/` + `modules/`）：**

| 层 | 定位 | 内容 |
|---|---|---|
| `core/` | 纯组件（无业务状态、无 DB 表语义） | `db_client.py`（连接池）、`http_utils.py`（HTTP 重试/限速/类型转换）、`retry_utils.py`（指数退避）、`batch_utils.py`（切片）、`local_buffer.py`（本地缓冲）。进度可视化统一用 `tqdm`，不再自建进度日志组件 |
| `modules/` | 跨家族业务模块（有 DB 表/业务规则语义） | `sync_log.py`（同步状态追踪）、`db_admin.py`（管理查询/DDL） |

**判断标准：** 不依赖特定表结构/业务规则 → `core/`；依赖 sync_log 等业务表语义 → `modules/`。

**三条模块家族：**

| 家族 | 入口 | 扩展点模式 | 客户端/限速层 |
|---|---|---|---|
| `data/` 日线主流程 | `data/pipeline.py` | 新市场 MUST 实现 `MarketModule` protocol（见下），在 `data/market_*.py` 实现，`pipeline.py` 里注册 | 各 `market_*.py` 自带；跨市场共享逻辑放 `core/http_utils.py` / `data/index_base.py`；所有 yfinance 调用 MUST 走 `data/yf_client.py`（限速+重试），不得自建 retry 循环 |
| `ts_ingest/` Tushare 回填 | `ts_ingest/orchestrator.py`（phase: lists→prices→derive→financial→valuation） | 新回填域 MUST 新建 `ts_ingest/backfill_<domain>.py`，暴露 `backfill_all()`，在 orchestrator 里按 phase 顺序挂载 | `ts_ingest/client.py`（限速+重试）+ `ts_ingest/budget.py`（调用预算），MUST 复用，不得自建 API 调用逻辑 |
| `futu_ingest/` Futu 回填 | `futu_ingest/orchestrator.py`（`run_sync(scope)` 分发表） | 新数据域 MUST 新建 `futu_ingest/backfill_<domain>.py` 或 `snapshot_<domain>.py`，暴露 `backfill_all()`/`run_daily()`，在 orchestrator 的 `want()` 分发表里挂 scope | `futu_ingest/client.py` + `futu_ingest/concurrency.py`；本地缓冲复用 `core/local_buffer.py`（断网本地优先，收尾 flush 到 NAS） |

**`MarketModule` protocol**（`data/pipeline.py` 定义，`market_us.py`/`market_cn.py`/`market_hk.py` 各自实现）：
`update_index()` / `list_active_tickers()` / `backfill_new(tickers)` / `incremental(tickers)` / `update_index_price()` / `rebase(tickers)` / `weekly(tickers)` / `intraday()`

**强制规则：**
1. 新市场/新数据源 MUST 走对应家族的既有 protocol/orchestrator 接入点，不得在 `main.py` 里直接写一次性脚本逻辑。
2. 跨市场/跨模块共享逻辑复用 `core/http_utils.py`（HTTP 重试/限速/类型转换）、`data/index_base.py`（成分股快照通用操作）；不得每个市场模块各写一份重复代码。
3. 数据库访问统一走 `core/db_client.py`（`query`/`execute`/`get_conn` 连接池），不得散落裸 `pymysql` 连接。同步状态追踪用 `modules/sync_log.py`。
4. 每个新增 backfill/updater/snapshot 模块 MUST 有对应 `tests/test_<module>.py`（现有 1:1 命名约定，见 `tests/` 目录）。
5. 不确定该归入哪个家族、或是否需要新建第四套平行结构 → 先问用户，不要自行决定。

详细字段/表/命令见 README.md「架构设计」「数据源明细」章节；本节是强制执行层，README 是描述层。

## Configuration

Secrets in `.env` (see `.env.example`). `DB_PASSWORD` and `TUSHARE_TOKEN` are required.

History depths in `config.py`: US=5yr, CN/HK=15yr from 2010-01-01.

Retry/delay settings in `config.py`: `AKSHARE_RETRY_COUNT=5`, `AKSHARE_RETRY_DELAY=3.0`, `AKSHARE_REQUEST_DELAY=1.5`.

Tushare rate limiting in `config.py`: `TUSHARE_RATE_INTERVAL=0.12` (每分钟最多 500 次).

## Network Notes

The codebase clears proxy environment variables in `main.py` (sets `NO_PROXY=*`) to avoid macOS system proxy interference with akshare/efinance HTTP requests to eastmoney.com APIs.

## Database

MariaDB on Synology NAS. `core/db_client.py` 通过 DBUtils.PooledDB 连接池管理连接，`setsession=["SET time_zone = '+08:00'"]` 在新建物理连接时执行。同步状态追踪见 `modules/sync_log.py`（`sync_log` 表 CRUD）。

Tables: `stocks`, `prices`, `indices`, `index_constituents`, `constituent_changes`, `index_prices`, `index_sync_log`, `sync_log`.

**stocks 表字段:**
- `ticker` — 主键（canonical format）
- `name` — 股票名称
- `gics_sector` — 行业分类（tushare `stock_basic.industry`）
- `exchange` — 交易所（SH/SZ/BJ/HK/US）