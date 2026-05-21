# 美股周线采集 — 设计文档

**日期：** 2026-05-21  
**范围：** US 市场，新增周线（1wk）采集，不影响现有日线逻辑

---

## 目标

为 SP500 + Russell 1000 成分股新增周线（`prices_weekly`）采集能力，通过独立 CLI 命令触发，与日线流程完全隔离。

---

## 架构

### 文件变动

| 文件 | 变动类型 | 说明 |
|---|---|---|
| `data/stock_updater_us_weekly.py` | **新建** | 周线下载 + 写库，完全镜像日线逻辑 |
| `data/market_us.py` | **追加** | 新增 `weekly()` 函数，不改现有函数 |
| `main.py` | **追加** | 新增 `weekly` 子命令 |

`data/stock_updater_us.py` / `data/pipeline.py` / `db.py` **零改动**。

### 数据流

```
main.py weekly --market us
  └─ cmd_weekly(market, codes)
       └─ market_us.weekly(tickers)
            └─ stock_updater_us_weekly.update_weekly_batch(tickers)
                 ├─ AAPL 预检（测最近周是否有数据）
                 ├─ yf.download(interval="1wk", group_by="ticker")
                 ├─ INSERT IGNORE → prices_weekly
                 └─ sync_log (data_type="price_weekly")
```

---

## 实现细节

### `data/stock_updater_us_weekly.py`

完全镜像 `stock_updater_us.py`，差异仅：

| 项目 | 日线 | 周线 |
|---|---|---|
| yfinance interval | `"1d"` | `"1wk"` |
| 写入表 | `prices` | `prices_weekly` |
| sync_log data_type | `"price"` | `"price_weekly"` |
| 历史起点 | `START_DATE_US` (2010-01-01) | 同 `START_DATE_US` |
| 增量窗口上限 | `YF_LOOKBACK_DAYS` (7天) | 同 `YF_LOOKBACK_DAYS` |

AAPL 预检逻辑：测试最近已收盘周（即最近周五）的周线数据是否存在，限速则跳过整批。

`get_last_sync(conn, ticker, "price_weekly")` 对 `price_weekly` 无 fallback（现有 `get_last_sync` 仅对 `"price"` 做 fallback 到 `prices` 表），返回 `None` 时触发全量回填（从 `START_DATE_US` 起）。

### `data/market_us.py` 新增

```python
def weekly(tickers: list[str] | None = None) -> dict[str, str]:
    from data import stock_updater_us_weekly
    targets = tickers or list_active_tickers()
    return stock_updater_us_weekly.update_weekly_batch(targets)
```

不改现有任何函数。

### `main.py` 新增子命令

```bash
uv run main.py weekly --market us           # 全量增量（SP500 + R1000）
uv run main.py weekly --market us --code AAPL  # 单票调试
```

`weekly` 子命令仅支持 `--market us`（CN/HK 暂不实现）。  
无 `--index` 参数（周线始终覆盖完整 universe）。

---

## 数据库

`prices_weekly` 表已存在（`sql/001_tushare_tables.sql`），结构：

```sql
CREATE TABLE IF NOT EXISTS prices_weekly (
    ticker  VARCHAR(20) NOT NULL,
    date    DATE        NOT NULL,   -- 周一日期（yfinance 返回）
    open    DECIMAL(10,4),
    high    DECIMAL(10,4),
    low     DECIMAL(10,4),
    close   DECIMAL(10,4),
    volume  BIGINT,
    PRIMARY KEY (ticker, date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

无需 DDL 变更。

---

## 运行频率

每天触发（与日线 cron 并列），yfinance 周线仅周五收盘后有新数据，其他交易日增量检查后快速跳过（无新数据，`sync_log` 已是最新周）。

---

## 不在范围内

- CN/HK 周线
- 月线
- 周线指数价格（`index_prices` 表无 interval 字段，暂不扩展）
- `rebase` 子命令对周线的支持
