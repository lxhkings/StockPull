# StockPull — 多市场股票数据同步系统

三市场（美股/A股/港股）日线 + 周线数据采集，写入群辉 NAS MariaDB（192.168.8.9:3306）。

## 目录

- [快速开始](#快速开始)（新机器/首次搭建）
- [日常使用](#日常使用)（每天/每周该跑什么）
- [首次配置 / 补历史数据](#首次配置--补历史数据)（一次性操作）
- [美股基本面数据 Futu OpenAPI](#美股基本面数据-futu-openapi)
- [数据库表](#数据库表)
- [架构设计](#架构设计)（给开发者看）
- [数据源明细](#数据源明细)
- [配置](#配置)
- [测试](#测试)
- [常见问题](#常见问题)

---

## 快速开始

- Python 3.12+（`.python-version` 指定）
- MariaDB on NAS（192.168.8.9:3306）
- uv（Python 包管理器）
- Tushare API Token（用于 A 股基础数据）

```bash
uv venv --python 3.12
source .venv/bin/activate
cp .env.example .env  # 填入 DB_PASSWORD 和 TUSHARE_TOKEN

uv run main.py init      # 初始化：插入指数元数据
uv run main.py daily     # 全市场增量同步
```

---

## 日常使用

**每天该跑的（美股收盘后 / cron）：**

```bash
uv run main.py daily --market us   # 美股默认组合（SP500 + R1000，约1016支）
uv run main.py daily --market us --index SP500      # 仅 SP500 成分股（503支）
uv run main.py daily --market us --index RUSSELL1000 # 仅 Russell 1000（1008支）
uv run main.py daily --market cn   # A股（CSI800），自动包含 CN 行业 ETF
uv run main.py daily --market hk   # 港股（HSI）
uv run main.py daily               # 全市场（默认）
```

Cron 示例（北京时间每日 18:00，美股收盘后）：

```bash
0 18 * * 1-5 /path/to/project/scripts/daily_update.sh >> /var/log/stocks.log 2>&1
```

美股交易日计算：程序自动算最近已收盘的交易日（北京时间凌晨5:00收盘；周一凌晨5点前用上周五数据；周末用周五数据）。日志写入 `logs/daily_YYYY-MM-DD.log`。

**每周该跑的（周线，`prices_weekly` 表）：**

```bash
uv run main.py weekly --market us   # 美股周线（SP500 + R1000，yfinance interval=1wk）
uv run main.py weekly --market cn   # A股周线（全量 A 股，tushare pro_bar freq=W）
uv run main.py weekly --market us --code AAPL      # 单票调试（美股）
uv run main.py weekly --market cn --code 600519.SH # 单票调试（A股）
```

**分钟线（`prices_intraday` 表，仅美股）：**

```bash
uv run main.py intraday                  # 默认：15m + 1h
uv run main.py intraday --interval 1h    # 仅 1h（730天最大历史）
uv run main.py intraday --interval 15m   # 仅 15m（60天最大历史）
uv run main.py intraday --interval 1h --rebase  # 全量回补，忽略 sync_log
```

**查看同步状态：**

```bash
uv run main.py status
```

**A股中报/年报出来后（8月底、次年4月前后），补最新一期财务数据：**

```bash
uv run main.py tushare-backfill --scope financial
uv run trendspec ingest fundamentals --market cn   # (在 TrendSpec 仓库里跑，把数据摄入下游 data_lake)
```

---

## 首次配置 / 补历史数据

这些是一次性操作：新机器搭建、补历史缺口、或数据结构升级后重新回填。

**全量回补（qfq 复权漂移修复，或首次拉历史）：**

```bash
uv run main.py rebase --market cn  # A股全量重拉（tushare qfq，默认15年）
uv run main.py rebase --market hk  # 港股全量重拉（yfinance auto_adjust，默认15年）
uv run main.py rebase --market us  # 美股全量重拉（yfinance raw，2010年起，1016支）
uv run main.py rebase --market us --index SP500  # 仅 SP500 成分股
uv run main.py rebase --market us --years 10  # 指定10年历史
uv run main.py rebase --market cn --code 600519.SH  # 单只股票全量重拉
uv run main.py rebase --market cn --etf-only   # 仅 CN 行业 ETF 全量重灌（季度执行，修正分红drift）
```

**Tushare 回填（股票基础信息 + 行业分类 + 财务数据 + 估值数据）：**

```bash
uv run main.py tushare-backfill --scope lists --market cn  # A股基础信息（含行业分类+list_date/delist_date）
uv run main.py tushare-backfill --scope lists --market hk  # 港股基础信息
uv run main.py tushare-backfill --scope derive              # 周线/月线聚合（从日线计算）
uv run main.py tushare-backfill --scope financial           # 财务三表+指标（income/balancesheet/cashflow/indicator）
uv run main.py tushare-backfill --scope valuation           # 每日估值快照（PE/PB/PS，daily_basic）
uv run main.py tushare-backfill --scope valuation --start 20100101  # 强制重新回填估值历史（见下方⚠️）
uv run main.py tushare-backfill --dry-run                   # 预检（不执行）
```

- `stocks.list_date`/`delist_date`（全A股 universe 前置）已并入 `--scope lists`（跑在 stocks_a/hk/us 之后，脚本已保证顺序）。只想单独补这两列：
  ```bash
  uv run python3 -c "from ts_ingest.backfill_stock_dates import backfill_stock_dates; print(backfill_stock_dates())"
  ```
- `financial`/`valuation` 均可安全重复运行（幂等）：
  - `financial` 按季度全量重算（低频，全市场单期批量，~66期×4接口，约3小时）
  - `valuation` 默认增量（从 `cn_valuation_snapshot` 里已有的最新交易日之后开始拉）；首次运行/表为空时才会从2010年全量回填（~13小时）
  - `--start YYYYMMDD` 可强制指定起点重新回填历史（financial/valuation 均支持）

⚠️ **`--start` 强制回填历史很慢，且可能触发NAS慢查询**——见[常见问题](#常见问题)。

日线数据不走这个命令，通过 `daily`/`rebase` 拉取（CN: tushare, HK/US: yfinance）。

---

## 美股基本面数据 (Futu OpenAPI)

供下游量化项目做回测因子库。本项目只负责取数入库，不算因子。

```bash
# 全量采集（首次/重建）
uv run main.py futu-full                    # 全量采集（所有 scope，~10h）
uv run main.py futu-full --scope financial  # 仅财务4表（~4.5h）
uv run main.py futu-full --scope other      # 除财务表外的全部（~5.5h）

# 增量同步（cron 每日；按接口频率节流）
uv run main.py futu-sync                    # 增量同步（所有 scope）
uv run main.py futu-sync --scope daily      # 仅日频快照

# 恢复工具（NAS 宕机/网络中断后）
uv run main.py futu-flush                   # 把本地缓冲重放到 NAS
```

**工作流说明：**
- futu-full/futu-sync 采集过程：先写本地缓冲 `.futu_buffer/pending.sqlite`
- 采集完成后自动 flush 到 NAS（MariaDB）
- NAS 宕机或网络中断 → flush 失败，数据保留在本地缓冲
- NAS 恢复后：运行 `futu-flush` 将本地缓冲重新同步到 NAS（无数据丢失）

**Scope 选项：**

| scope | 内容 |
|---|---|
| `all` | 全部 22 张表 |
| `other` | 除 financial 外的 18 张表（已采 financial 后使用） |
| `financial` | 财务4表（利润表/资产负债表/现金流量表/关键指标） |
| `earnings` | 财报发布日 + PIT 回填 |
| `actions` | 分红/拆股 |
| `profile` | 公司元数据 |
| `revenue` | 分部营收 + 财报日涨跌 |
| `shareholders` | 5张股东相关表 |
| `efficiency` | 运营效率 |
| `daily` | 6张日频快照（流通股/分析师/资金流/卖空） |
| `weekly` | 3张周频快照（估值/评级/Morningstar） |

前提：本地 OpenD 运行于 `127.0.0.1:11111`，美股行情权限 ≥ LV1。

### ⚠️ Point-in-Time（回测必读）

财务表有两个日期：
- `period_end`：报告期末（财报覆盖到哪天）
- `ann_date`：**发布日**（财报实际公布日，晚于 period_end）

**回测取财务数据必须按发布日过滤，否则用到未来数据：**

```sql
-- ✅ 正确：某回测日 D 能看到的最新年报净利润
SELECT raw_payload
FROM us_fin_income
WHERE ticker = 'AAPL'
  AND financial_type = '7'        -- 7=年报
  AND ann_date <= '2024-06-30'    -- 回测日 D，只用已发布的
ORDER BY period_end DESC
LIMIT 1;

-- ❌ 错误：按 period_end 过滤会用到尚未公布的财报
```

### 复权价计算（下游自算）

本项目美股 `prices` 表是**不复权**原始价。复权由下游用 `us_dividends` + `us_splits` 事件自算（CRSP 标准总收益复权），本项目不存复权因子。

### 财务科目字段对照

`raw_payload.item_list` 里 `field_id` 的含义，查 Futu 字段表或调用接口的 `structure_list`（含 `field_id` → `display_name` 映射）。

---

## 数据库表

MariaDB 时区设置：`+08:00`（每连接设置）。

**核心表（三市场通用）：**

| 表 | 内容 |
|---|---|
| `stocks` | 股票基础信息（ticker, name, gics_sector, exchange, list_date, delist_date） |
| `prices` | 日线数据（date, ticker, open, high, low, close, volume） |
| `prices_weekly` | 周线数据（同 prices 结构；美股=yfinance 1wk，A股=tushare freq=W） |
| `prices_intraday` | 分钟线数据（ticker, interval, datetime, open, high, low, close, volume；仅美股） |
| `indices` | 指数元数据 |
| `index_constituents` | 成分股快照（index_id, snapshot_date, ticker, name, sector） |
| `constituent_changes` | 成分股变动记录（ADDED/REMOVED） |
| `index_prices` | 指数日线（含美股ETF + CN行业ETF，见下方数据源明细） |
| `sync_log` | 股票同步状态（ticker, last_date, status） |
| `index_sync_log` | 指数同步状态 |

**CN财务/估值表：**

| 表 | 内容 | 来源 |
|---|---|---|
| `fin_income` / `fin_balancesheet` / `fin_cashflow` / `fin_indicator` | A股财务三表+指标（ts_code, end_date, ann_date, raw_payload JSON） | Tushare `*_vip` 全市场单期接口 |
| `cn_valuation_snapshot` | A股每日估值快照（ts_code, trade_date, pe/pe_ttm/pb/ps/ps_ttm/total_mv/circ_mv） | Tushare `daily_basic` 全市场单日接口 |

**US基本面表（Futu，22张）：** 见 [美股基本面数据](#美股基本面数据-futu-openapi) 一节的完整表清单。

- `ticker` 在US基本面表里为 canonical 格式，**无前缀**（如 `AAPL`、`BRK.B`）
- 每张表都有 `raw_payload` (JSON)，存接口返回的全部原始字段

---

## 架构设计

```
main.py
  └── data/pipeline.py        # Pipeline 流程编排
        ├── data/market_us.py  # 美股适配器（yfinance，SP500+R1000组合）
        ├── data/market_cn.py  # A股适配器（tushare）
        └── data/market_hk.py  # 港股适配器（本地 CSV + yfinance）

data/yf_client.py                # yfinance 请求封装（限速+重试，对齐 ts_ingest/futu_ingest 的 client.py）
data/stock_updater_us_weekly.py  # 美股周线（yfinance 1wk → prices_weekly）
data/stock_updater_cn_weekly.py  # A股周线（tushare freq=W → prices_weekly）
data/intraday_updater_us.py      # 美股分钟线（yfinance 15m/60m → prices_intraday）

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
- `weekly(tickers)` — 周线增量采集（US/CN，写 prices_weekly）
- `intraday()` — 分钟线增量采集（仅 US，写 prices_intraday）

---

## 数据源明细

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

**美股行业 ETF（`index_prices` 表，`daily --market us` 自动采集）：**

QQQ (纳斯达克100) / XLK (科技) / XLY (可选消费) / XLF (金融) / XLV (医疗) / XLP (必选消费) / XLI (工业) / XLE (能源) / XLB (材料) / XLRE (房地产) / XLU (公用事业) / XLC (通信服务)

**CN 行业 ETF（`index_prices` 表，`index_id` 为 ts_code）：**

A股行业 ETF 后复权日线（hfq close）via tushare `fund_daily × fund_adj`。清单：`config.CN_SECTOR_ETFS`，按 GICS 11 类对齐 US XL* + A股主题（光伏/新能源车/芯片），共 ~17 只。

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

**数据库查询示例（Python）：**

```python
from db import query, execute

# SELECT（返回 list[dict]）
rows = query("SELECT ticker, name, gics_sector FROM stocks WHERE exchange = 'SH' LIMIT 10")

# SELECT with 参数
etf_data = query(
    "SELECT index_id, MIN(date), MAX(date), COUNT(*) FROM index_prices "
    "WHERE index_id IN (%s, %s) GROUP BY index_id",
    ('XLK', 'XLY')
)

# INSERT/UPDATE/DELETE（返回影响行数）
rows_affected = execute(
    "INSERT INTO stocks (ticker, name, exchange) VALUES (%s, %s, %s)",
    ('AAPL', 'Apple Inc', 'US')
)

# 批量插入
rows = [('AAPL', '2026-05-23', 180.50), ('MSFT', '2026-05-23', 420.30)]
rows_affected = execute(
    "INSERT INTO prices (ticker, date, close) VALUES (%s, %s, %s)", rows, many=True
)

# 常用查询函数
from db import get_index_tickers, get_latest_snapshot_tickers
sp500_tickers = get_index_tickers('SP500')
latest_tickers = get_latest_snapshot_tickers('CSI800')
```

命令行快速查询：

```bash
python3 -c "from db import query; print(query('SELECT COUNT(*) as count FROM prices')[0]['count'])"
mysql -h 192.168.8.9 -u root -p stocks
```

---

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

`main.py` 清除代理环境变量（设置 `NO_PROXY=*`），避免 macOS 系统代理干扰 tushare/yfinance API 请求。

---

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

---

## 常见问题

**`tushare-backfill --scope valuation --start` 卡很久 / 没反应？**

大概率不是卡死，是真的在跑但很慢。`_trading_dates()`（`ts_ingest/backfill_valuation.py`）用 `ticker LIKE '%.SH'` 这类前导通配符查 `prices` 表取全部A股交易日，这种写法走不了索引，在百万级行的表上是全表扫描+排序，群辉NAS性能有限，可能要跑几分钟到十几分钟。用 `SHOW PROCESSLIST` 连 NAS 能看到真实活跃查询（状态 `Sending data`/`Creating sort index` 说明还在跑，不是挂起）。这是既有实现的效率问题，不是bug，只是耗时长，等它跑完即可。

**为什么 `fund_pe_ttm` 类估值因子多年回测跑不出结果？**

`cn_valuation_snapshot` 默认增量拉取，只有从**第一次跑 `--scope valuation`** 那天起的数据（不会自动补历史）。要做2020-2026这种多年回测，必须显式 `--start 20100101`（或更早）跑一次强制历史回填，否则早期日期查不到估值数据，因子直接为 null。

**`--scope lists`/`financial`/`valuation` 具体各更新什么，不要混淆：**

- `--scope lists`：股票/ETF/港股通名单 + 行业分类 + list_date/delist_date。**不含**财务、估值。
- `--scope financial`：财务报表（ROE等质量因子用）。
- `--scope valuation`：估值快照（PE/PB等因子用）。

`--scope all` 会依次跑完 lists → prices → derive → financial → valuation 全部阶段。

## 实现计划

详见 `docs/superpowers/plans/` 目录。
