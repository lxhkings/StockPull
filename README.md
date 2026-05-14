# StockPull — 多市场股票数据同步系统

三市场（美股/A股/港股）日线数据采集，写入群辉 NAS MariaDB（192.168.8.9:3306）。

## 系统要求

- Python 3.12+（`.python-version` 指定）
- MariaDB on NAS（192.168.8.9:3306）
- uv（Python 包管理器）
- Tushare API Token（用于 A 股基础数据）

## 快速开始

```bash
# 使用 uv 管理 Python 版本和依赖
uv venv --python 3.12
source .venv/bin/activate
cp .env.example .env  # 填入 DB_PASSWORD 和 TUSHARE_TOKEN

uv run main.py init      # 初始化：插入指数元数据
uv run main.py daily     # 全市场增量同步
```

## CLI 命令

```bash
# 日常增量同步
uv run main.py daily --market us   # 美股全部（5927支）
uv run main.py daily --market us --index SP500  # 仅 SP500 成分股
uv run main.py daily --market cn   # A股
uv run main.py daily --market hk   # 港股
uv run main.py daily               # 全市场（默认）

# 初始化与状态
uv run main.py init                # 初始化指数元数据
uv run main.py status              # 查看同步状态

# 全量回补（hfq 漂移修复）
uv run main.py rebase --market cn  # A股全量重拉（tushare hfq，默认15年）
uv run main.py rebase --market hk  # 港股全量重拉（yfinance hfq，默认15年）
uv run main.py rebase --market us  # 美股全量重拉（yfinance raw，默认5年，5927支）
uv run main.py rebase --market us --index SP500  # 仅 SP500 成分股
uv run main.py rebase --market us --years 10  # 指定10年历史
uv run main.py rebase --market cn --code 600519.SH  # 单只股票全量重拉

# Tushare 回填（股票基础信息+行业分类+财务数据）
uv run main.py tushare-backfill --scope lists --market all  # 全市场基础信息（CN/HK/US + ETF）
uv run main.py tushare-backfill --scope derive              # 周线/月线聚合（从日线计算）
uv run main.py tushare-backfill --scope financial           # 财务数据
uv run main.py tushare-backfill --dry-run                   # 预检（不执行）

# 注：日线数据通过 daily/rebase 命令拉取（CN: tushare, HK/US: yfinance）
```

## 架构设计

```
main.py
  └── data/pipeline.py        # Pipeline 流程编排
        ├── data/market_us.py  # 美股适配器（yfinance）
        ├── data/market_cn.py  # A股适配器（tushare）
        └── data/market_hk.py  # 港股适配器（本地 CSV + yfinance）

data/index_updater_*.py        # 各市场成分股快照
ts_ingest/backfill_lists.py    # Tushare 股票列表回填
ts_ingest/client.py            # Tushare API 客户端（限速+重试）
ts_ingest/backfill_prices.py   # Tushare 日线回填
db.py                          # 数据库连接池
config.py                      # 配置管理
```

每个市场模块遵循 `MarketModule` 协议：
- `update_index()` — 成分股快照，检测新增/剔除
- `list_active_tickers()` — 当前股票池
- `backfill_new(tickers)` — 新股全量历史
- `incremental(tickers)` — 存量股票增量（从 sync_log 恢复）
- `update_index_price()` — 指数日线
- `rebase(tickers)` — 全量重拉（修复 hfq 漂移）

## 数据源

| 市场 | 指数成分股 | 股票价格 | 指数价格 | 行业分类 |
|------|-----------|---------|---------|---------|
| 美股 | GitHub CSV (SP500) | yfinance | yfinance ^GSPC | N/A |
| A股 | tushare `index_weight` | tushare `pro_bar` (hfq) | tushare `index_daily` | tushare `stock_basic.industry` |
| 港股 | 本地 CSV (HSI) | yfinance hfq | yfinance ETF | N/A |

**HSI 成分股维护：**
- 文件：`data/hsi_constituents.csv`
- 手动更新：参考 https://en.wikipedia.org/wiki/Hang_Seng_Index

## 价格校验

（已废弃，原 akshare/efinance 双源校验功能）

## Cron 定时任务

```bash
# 北京时间每日 18:00（美股收盘后）
0 18 * * 1-5 /path/to/project/scripts/daily_update.sh >> /var/log/stocks.log 2>&1
```

**美股交易日计算：**
- 北京时间凌晨 5:00 美股收盘
- 程序自动计算最近已收盘的交易日
- 周一凌晨 5:00 前 → 上周五数据
- 周六/周日 → 周五数据

日志写入 `logs/daily_YYYY-MM-DD.log`。

## 配置

所有敏感信息在 `.env`（参考 `.env.example`）：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| DB_HOST | 192.168.8.9 | MariaDB 主机 |
| DB_PORT | 3306 | MariaDB 端口 |
| DB_USER | root | 用户名 |
| DB_PASSWORD | **必填** | 密码 |
| DB_NAME | stocks | 数据库名 |
| TUSHARE_TOKEN | **必填** | Tushare API Token |

历史深度配置（`config.py`）：
- 美股：5 年
- A股/港股：15 年（从 2010-01-01 起）

Tushare 限速（`config.py`）：`TUSHARE_RATE_INTERVAL=0.12`（每分钟最多 500 次 API 调用）

## 数据库表

MariaDB 时区设置：`+08:00`（每连接设置）。

核心表：
- `stocks` — 股票基础信息（ticker, name, gics_sector, exchange）
- `prices` — 日线数据（date, ticker, open, high, low, close, volume）
- `indices` — 指数元数据
- `index_constituents` — 成分股快照（index_id, snapshot_date, ticker, name, sector）
- `constituent_changes` — 成分股变动记录（ADDED/REMOVED）
- `index_prices` — 指数日线
- `sync_log` — 股票同步状态（ticker, last_date, status）
- `index_sync_log` — 指数同步状态

## 测试

```bash
uv run pytest tests/ -v
```

覆盖：ticker 格式转换、配置、数据库、Pipeline、指数更新、股票更新、价格校验、CLI。

单模块测试：
```bash
uv run pytest tests/test_index_updater_cn.py -v
uv run pytest tests/test_cn_index_price.py -v
```

## 网络注意事项

`main.py` 清除代理环境变量（设置 `NO_PROXY=*`），避免 macOS 系统代理干扰 tushare/yfinance API 请求。

## 实现计划

详见 `docs/superpowers/plans/` 目录。