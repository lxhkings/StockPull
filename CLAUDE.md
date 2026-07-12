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
uv run pytest tests/test_market_cn_etf_hook.py -v  # single file
uv run pytest tests/test_etf_updater_cn.py -v      # CN sector ETF prices

# CLI（二级命令：prices | tushare | futu | init | status | db）
uv run main.py init                         # one-time: seed index metadata
uv run main.py prices daily                 # all markets
uv run main.py prices daily --market us
uv run main.py prices daily --market cn     # single market
uv run main.py prices daily --market cn --code 600519.SH  # single ticker (debug)
uv run main.py prices rebase --market cn    # full hfq re-pull
uv run main.py prices weekly --market us
uv run main.py prices intraday              # US 分钟线
uv run main.py status                       # DB sync summary
uv run main.py db migrate-intraday          # create prices_intraday table
uv run main.py db purge-index --index-id CSI800          # dry-run 统计
uv run main.py db purge-index --index-id CSI800 --yes    # 确认删除

# Futu 美股基本面
uv run main.py futu full             # 全量采集（首次/重建）
uv run main.py futu full --scope financial
uv run main.py futu sync             # 增量（按接口频率节流；手动按需）
uv run main.py futu sync --scope daily
uv run main.py futu flush            # 兜底：把本地缓冲重放到 NAS（futu full/sync flush 失败后）

# futu full/sync 先写本地缓冲（.futu_buffer/pending.sqlite），收尾自动 flush 到 NAS。
# NAS 中途宕机不丢数据；flush 失败时跑 futu flush 兜底。

# Tushare 回填（股票基础信息、行业分类、财务、估值、股东回报）
uv run main.py tushare sync --scope lists --market cn  # 增量/日常用
uv run main.py tushare full --scope valuation          # 全量强制回填（--start 2010起）
uv run main.py tushare sync --scope valuation --start 20200101  # 自定义起点
uv run main.py tushare flush                           # 本地缓冲重放到 NAS
# tushare * / futu * / prices daily：均手动按需；仓库内无 cron 包装脚本
```

## Architecture

Three-market daily-K ingest (US/CN/HK) into shared MariaDB on Synology NAS (192.168.8.9:3306).

**主轴：`apis/*`（按上游 API）+ `jobs/*`（编排）+ `core/`/`modules/`（共享组件）。**

**Pipeline flow** (`jobs/pipeline.py`):
1. `update_index()` — snapshot index constituents, detect added/removed
2. `backfill_new()` — full history for new tickers
3. `incremental()` — resume from sync_log for existing tickers
4. `update_index_price()` — index daily close
5. `weekly()` / `intraday()` — optional when market module implements them

**Market modules** follow `MarketModule` protocol (defined in `jobs/pipeline.py`):
- `jobs/market_us.py` — 编排 `apis.static`（SP500/R1000）+ `apis.yfinance`（日线/周线/分钟线/prices_index）
- `jobs/market_cn.py` — 编排 `apis.tushare`（全 A 列表/日线/周线 + 行业 ETF 价）
- `jobs/market_hk.py` — 编排 `apis.static`（HSI CSV）+ `apis.yfinance`（港股日线）

**CN Market 数据源：**
- 股票宇宙: 全 A（tushare `stock_basic`，非指数成分）
- A股基础信息: tushare `stock_basic` API（含行业分类 `industry` 字段）
- A股日线价格: tushare `pro_bar` API (hfq)
- 行业 ETF 价: tushare `fund_daily` × `fund_adj` → `index_prices`（index_id = ts_code）

**HK Market 数据源：**
- HSI 成分股: 本地 CSV `apis/static/hsi_constituents.csv`（手动维护）
- 港股日线价格: yfinance

**Key patterns:**
- CN/HK prices are hfq (后复权/post-adjusted); US prices are raw
- `ON DUPLICATE KEY UPDATE` for stocks table (更新 name 和 gics_sector)
- `INSERT IGNORE` for index_constituents (daily snapshots)
- `sync_log` table tracks per-ticker last successful sync date
- `index_constituents` table stores daily snapshots with `snapshot_date`
- `constituent_changes` table tracks ADDED/REMOVED diffs
- `gics_sector` column in stocks table filled by tushare `stock_basic.industry`

**Ticker formats** (`apis/yfinance/ticker_utils.py`):
- Canonical: `600519.SH`, `00700.HK`, `AAPL`
- tushare A-share: `600519.SH` (与 canonical 一致)

## 扩展新功能前必读（强制）

新增/修改功能前，先判断属于哪一层，MUST 遵循既有模式，不允许绕过或新建平行顶层包。

**共享层（`core/` + `modules/`）：**

| 层 | 定位 | 内容 |
|---|---|---|
| `core/` | 纯组件（无业务状态、无 DB 表语义） | `db_client.py`（连接池）、`http_utils.py`（HTTP 重试/限速/类型转换）、`retry_utils.py`（指数退避）、`batch_utils.py`（切片）、`local_buffer.py`（本地缓冲）、`trading_calendar.py`（US/CN 交易日）。进度可视化统一用 `tqdm` |
| `modules/` | 跨源业务模块（有 DB 表/业务规则语义） | `sync_log.py`（同步状态追踪，含 bulk 读）、`db_admin.py`（管理查询/DDL）、`index_base.py`（成分股快照/stocks 注册）、`price_write.py`（价格+sync 批写） |

**判断标准：** 不依赖特定表结构/业务规则 → `core/`；依赖 sync_log 等业务表语义 → `modules/`。

**分层与依赖方向（强制）：**

```
main.py     → jobs, apis.*.orchestrator, core, modules, config
jobs/*      → apis.*, core, modules, config   ❌ yfinance/tushare/futu SDK
apis/<src>/*→ core, modules, config, 同包内   ❌ 跨 apis 互引；❌ import jobs
core/*      → stdlib / 第三方 / config        ❌ jobs, apis, modules
modules/*   → core, config                    ❌ jobs, apis
```

| 层 | 入口 | 扩展点模式 | 客户端/限速层 |
|---|---|---|---|
| `apis/yfinance` | 各 `prices_*.py` / `client.py` | 新 yf 接口 MUST 放本包；调用 MUST 走 `apis.yfinance.client`（限速+重试） | `apis/yfinance/client.py` |
| `apis/tushare` | `apis/tushare/orchestrator.py`（phase: lists→prices→derive→financial→valuation…） | 新回填域 MUST 新建 `backfill_<domain>.py`（+ 可选 `transform_*`），挂 orchestrator | `client.py` + `budget.py` |
| `apis/futu` | `apis/futu/orchestrator.py`（`run_sync(scope)` 分发表） | 新域 MUST 新建 `backfill_*` / `snapshot_*`，在 orchestrator `want()` 挂 scope | `client.py` + `concurrency.py`；缓冲 `core/local_buffer.py` |
| `apis/static` | `sp500_github` / `russell_ishares` / `hsi_csv` | 仅成分股**源适配**；写表 MUST 走 `modules.index_base` | 无 SDK |
| `jobs/` 日线编排 | `jobs/pipeline.py` | 新市场 MUST 实现 `MarketModule`，在 `jobs/market_*.py`；只调 apis，不调 SDK | — |

**`MarketModule` protocol**（`jobs/pipeline.py` 定义，`jobs/market_{us,cn,hk}.py` 各自实现）：
`update_index()` / `list_active_tickers(index: str | None = None)` / `backfill_new(tickers)` / `incremental(tickers)` / `update_index_price()` / `rebase(tickers)` / `weekly(tickers)` / `intraday()`

- **`list_active_tickers(index=...)`：** US 解析 `SP500`/`RUSSELL1000`/默认并集；**CN/HK 的 `index` 参数忽略**（单 universe，docstring 须写明）。

### 扩展 checklist

**同一 API 新接口/新表：**
1. `apis/<src>/backfill_<domain>.py` 或 `snapshot_*.py` / `prices_*.py`
2. 可选 `transform_<domain>.py`（纯函数零 I/O）
3. `apis/<src>/orchestrator.py` 挂 scope/phase
4. 新表则 `sql/0xx_*.sql`
5. `tests/test_<src>_<domain>.py`（1:1 约定）
6. README scope 表 + 本节 checklist 一行

**全新数据源：** `apis/<newsrc>/client.py` → backfill/snapshot → orchestrator → main 子命令；进 daily 只改 `jobs/market_*` 调 apis。

**新市场：** `jobs/market_xx.py` 实现 MarketModule；复用已有 `apis/*`；无新 API 则不新建 apis 包。

**强制规则：**
1. 新市场/新数据源 MUST 走 `jobs` protocol 或 `apis/*/orchestrator` 接入点，不得在 `main.py` 里直接写采集逻辑。
2. 跨源共享逻辑复用 `core/*` / `modules/*`；不得每个适配器各写一份。
3. 数据库访问统一走 `core/db_client.py`；同步状态用 `modules/sync_log.py`；价格批写用 `modules/price_write.py`。
4. 每个新增 backfill/updater/snapshot 模块 MUST 有对应 `tests/test_*.py`。
5. **禁止** `apis` import `jobs`；**禁止** `jobs` 直接 import 上游 SDK；**禁止** 跨 `apis` 子包互引；**禁止** 新建第四顶层 `xxx_ingest`。
6. 不确定该归入哪一层 → 先问用户，不要自行决定。

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