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
uv run main.py daily --market us   # 美股默认组合（SP500 + R1000，约1016支）
uv run main.py daily --market us --index SP500      # 仅 SP500 成分股（503支）
uv run main.py daily --market us --index RUSSELL1000 # 仅 Russell 1000（1008支）
uv run main.py daily --market cn   # A股（CSI800）
uv run main.py daily --market hk   # 港股（HSI）
uv run main.py daily               # 全市场（默认）

# 初始化与状态
uv run main.py init                # 初始化指数元数据
uv run main.py status              # 查看同步状态

# 全量回补（qfq 漂移修复）
uv run main.py rebase --market cn  # A股全量重拉（tushare qfq，默认15年）
uv run main.py rebase --market hk  # 港股全量重拉（yfinance auto_adjust，默认15年）
uv run main.py rebase --market us  # 美股全量重拉（yfinance raw，2010年起，1016支）
uv run main.py rebase --market us --index SP500  # 仅 SP500 成分股
uv run main.py rebase --market us --years 10  # 指定10年历史
uv run main.py rebase --market cn --code 600519.SH  # 单只股票全量重拉

# Tushare 回填（股票基础信息+行业分类+财务数据）
uv run main.py tushare-backfill --scope lists --market cn  # A股基础信息（含行业分类）
uv run main.py tushare-backfill --scope lists --market hk  # 港股基础信息
uv run main.py tushare-backfill --scope derive              # 周线/月线聚合（从日线计算）
uv run main.py tushare-backfill --scope financial           # 财务数据
uv run main.py tushare-backfill --dry-run                   # 预检（不执行）

# 注：日线数据通过 daily/rebase 命令拉取（CN: tushare, HK/US: yfinance）
```

## 架构设计

```
main.py
  └── data/pipeline.py        # Pipeline 流程编排
        ├── data/market_us.py  # 美股适配器（yfinance，SP500+R1000组合）
        ├── data/market_cn.py  # A股适配器（tushare）
        └── data/market_hk.py  # 港股适配器（本地 CSV + yfinance）

data/index_updater_*.py        # 各市场成分股快照
  ├── index_updater_us.py      # SP500（GitHub CSV）
  ├── index_updater_russell1000.py # Russell 1000（iShares CSV）
  ├── index_updater_cn.py      # CSI800（tushare）
  └── index_updater_hk.py      # HSI（本地 CSV）

ts_ingest/backfill_lists.py    # Tushare 股票列表回填（CN/HK）
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
- `rebase(tickers)` — 全量重拉（修复 qfq 漂移）

## 数据源

| 市场 | 指数成分股 | 股票价格 | 指数价格 | 行业分类 |
|------|-----------|---------|---------|---------|
| 美股 | GitHub CSV (SP500) + iShares CSV (R1000) | yfinance | yfinance ^GSPC | N/A |
| A股 | tushare `index_weight` | tushare `pro_bar` (qfq) | tushare `index_daily` | tushare `stock_basic.industry` |
| 港股 | 本地 CSV (HSI) | yfinance auto_adjust | yfinance ETF | N/A |

**美股指数组合策略：**
- 默认：SP500 + Russell 1000（约1016支大盘股）
- 可选单独指数：SP500（503支）或 RUSSELL1000（1008支）
- 数据源：SP500 使用 GitHub CSV，R1000 使用 iShares holdings CSV

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
- 美股：5 年（SP500 + R1000 组合，约1016支）
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

## 数据库操作

使用 `db.py` 模块操作数据库：

### Python 代码示例

```python
# 导入数据库模块
from db import query, execute

# SELECT 查询（返回 list[dict]）
rows = query(
    "SELECT ticker, name, gics_sector FROM stocks WHERE exchange = 'SH' LIMIT 10"
)
for row in rows:
    print(row['ticker'], row['name'])

# SELECT with 参数
etf_data = query(
    "SELECT index_id, MIN(date), MAX(date), COUNT(*) "
    "FROM index_prices WHERE index_id IN (%s, %s) "
    "GROUP BY index_id",
    ('XLK', 'XLY')
)

# INSERT/UPDATE/DELETE（返回影响行数）
rows_affected = execute(
    "INSERT INTO stocks (ticker, name, exchange) VALUES (%s, %s, %s)",
    ('AAPL', 'Apple Inc', 'US')
)

# 批量插入
rows = [
    ('AAPL', '2026-05-23', 180.50),
    ('MSFT', '2026-05-23', 420.30),
]
rows_affected = execute(
    "INSERT INTO prices (ticker, date, close) VALUES (%s, %s, %s)",
    rows,
    many=True  # 批量模式
)

# 常用查询函数
from db import get_index_tickers, get_latest_snapshot_tickers

# 获取指数成分股列表
sp500_tickers = get_index_tickers('SP500')  # 返回 list[str]

# 获取最新快照成分股
latest_tickers = get_latest_snapshot_tickers('CSI800')
```

### 命令行快速查询

```bash
# 使用 Python 交互式查询
python3 -c "
from db import query
result = query('SELECT COUNT(*) as count FROM prices')
print(result[0]['count'])
"

# 或者使用 mysql 命令行客户端
mysql -h 192.168.8.9 -u root -p stocks
```

### ETF 指数数据查询

项目支持 QQQ 和 11 个美国行业 ETF 指数数据，存储在 `index_prices` 表。

```python
# 查询所有 ETF 数据范围
etfs = ['QQQ','XLK','XLY','XLF','XLV','XLP','XLI','XLE','XLB','XLRE','XLU','XLC']
from db import query

etf_data = query(
    "SELECT index_id, MIN(date) as min_date, MAX(date) as max_date, COUNT(*) as count "
    "FROM index_prices "
    "WHERE index_id IN ('" + "','".join(etfs) + "') "
    "GROUP BY index_id ORDER BY index_id"
)
for row in etf_data:
    print(f"{row['index_id']}: {row['min_date']} ~ {row['max_date']} ({row['count']} rows)")

# 查询 QQQ 最新价格
qqq_latest = query(
    "SELECT date, close FROM index_prices "
    "WHERE index_id = 'QQQ' "
    "ORDER BY date DESC LIMIT 1"
)

# 查询 ETF 指数价格历史
qqq_history = query(
    "SELECT date, close FROM index_prices "
    "WHERE index_id = 'QQQ' AND date >= '2026-01-01' "
    "ORDER BY date"
)
```

**ETF 列表：**
- QQQ (纳斯达克100)
- XLK (科技)
- XLY (可选消费)
- XLF (金融)
- XLV (医疗)
- XLP (必选消费)
- XLI (工业)
- XLE (能源)
- XLB (材料)
- XLRE (房地产)
- XLU (公用事业)
- XLC (通信服务)

数据通过 `uv run main.py daily --market us` 自动采集，存储在 `index_prices` 表。

### CN 行业 ETF 数据

A股行业 ETF 后复权日线（hfq close）via tushare `fund_daily × fund_adj`，存 `index_prices` 表，`index_id` 为 ts_code（如 `512800.SH`）。

清单：`config.CN_SECTOR_ETFS`，按 GICS 11 类对齐 US XL* + A 股主题（光伏/新能源车/芯片），共 ~17 只。

跑法：

```bash
uv run main.py daily --market cn        # 自动包含 ETF
uv run main.py rebase --market cn --etf-only   # 仅 ETF 全量重灌（季度执行修正分红 drift）
```

查询示例：

```sql
-- CN vs US 同行业横向对比（银行 vs 美国金融）
SELECT date, index_id, close
FROM index_prices
WHERE index_id IN ('512800.SH', 'XLF')
  AND date >= '2026-01-01'
ORDER BY date, index_id;

-- 查 CN HealthCare 板块两只 ETF
SELECT date, index_id, close
FROM index_prices
WHERE index_id IN ('512170.SH', '512010.SH')
ORDER BY date;
```

ETF 列表：

| ts_code | 名称 | GICS / 主题 |
|---|---|---|
| 515220.SH | 煤炭ETF | Energy |
| 512400.SH | 有色金属ETF | Materials |
| 512660.SH | 军工ETF | Industrials |
| 159996.SZ | 家电ETF | ConsumerDiscretionary |
| 512690.SH | 酒ETF | ConsumerStaples |
| 512170.SH | 医疗ETF | HealthCare |
| 512010.SH | 医药ETF | HealthCare |
| 512800.SH | 银行ETF | Financials |
| 512000.SH | 券商ETF | Financials |
| 512720.SH | 计算机ETF | InformationTechnology |
| 512480.SH | 半导体ETF | InformationTechnology |
| 515050.SH | 5G通信ETF | CommunicationServices |
| 159611.SZ | 电力ETF | Utilities |
| 512200.SH | 房地产ETF | RealEstate |
| 515790.SH | 光伏ETF | Theme.Solar |
| 515030.SH | 新能源车ETF | Theme.NEV |
| 159995.SZ | 芯片ETF | Theme.Chip |

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