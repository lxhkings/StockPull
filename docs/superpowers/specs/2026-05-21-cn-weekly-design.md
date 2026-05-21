# A股周线采集 — 设计文档

**日期：** 2026-05-21  
**范围：** CN 市场，新增周线（freq=W）采集，不影响现有日线逻辑

---

## 目标

为全量 A 股新增周线（`prices_weekly`）采集能力。数据源 tushare `pro_bar(freq="W", adj="qfq")`，与日线完全对称。通过 `uv run main.py weekly --market cn` 触发。

---

## 架构

### 文件变动

| 文件 | 变动类型 | 说明 |
|---|---|---|
| `data/stock_updater_cn_weekly.py` | **新建** | CN 周线下载 + 写库，完全镜像 `stock_updater_cn_tushare.py` |
| `data/market_cn.py` | **追加** | 新增 `weekly()` 函数，不改现有函数 |
| `main.py` | **修改** | `weekly` 子命令 `--market` 扩展为 `us|cn` |

`data/stock_updater_cn_tushare.py` / `data/pipeline.py` **零改动**。

### 数据流

```
main.py weekly --market cn
  └─ cmd_weekly("cn", codes)
       └─ market_cn.weekly(tickers)
            └─ stock_updater_cn_weekly.update_weekly_batch(tickers)
                 ├─ tushare pro_bar(freq="W", adj="qfq")
                 ├─ ON DUPLICATE KEY UPDATE → prices_weekly
                 └─ sync_log (data_type="price_weekly")
```

---

## 实现细节

### `data/stock_updater_cn_weekly.py`

完全镜像 `stock_updater_cn_tushare.py`，差异仅：

| 项目 | 日线 | 周线 |
|---|---|---|
| tushare freq | `"D"` | `"W"` |
| 写入表 | `prices` | `prices_weekly` |
| SYNC_DATA_TYPE | `"price"` | `"price_weekly"` |
| 历史起点 | `TUSHARE_BACKFILL_START` (20100101) | 同 |
| batch commit size | 50 | 同 |
| `_last_cn_trading_date()` | 自有 | 复用（直接 import） |

写库 SQL 改为：
```sql
INSERT INTO prices_weekly (ticker, date, open, high, low, close, volume)
VALUES (%s, %s, %s, %s, %s, %s, %s)
ON DUPLICATE KEY UPDATE
    open=VALUES(open), high=VALUES(high), low=VALUES(low),
    close=VALUES(close), volume=VALUES(volume)
```

tushare `pro_bar(freq="W")` 返回的 `trade_date` 是该周**最后一个交易日**（通常周五）。`_normalize_pro_bar` 逻辑与日线完全相同，无需修改。

### `data/market_cn.py` 新增

```python
def weekly(tickers: list[str] | None = None) -> dict[str, str]:
    """Pull weekly prices for CN universe into prices_weekly."""
    from data import stock_updater_cn_weekly
    targets = tickers or list_active_tickers()
    return stock_updater_cn_weekly.update_weekly_batch(targets)
```

不改现有任何函数。

### `main.py` 修改

`_build_parser()` 中 `p_weekly` 的 `--market choices` 从 `("us",)` 改为 `("us", "cn")`。

`cmd_weekly()` 不需要改动——已通过 `mod = _import_market(market)` + `mod.weekly()` 统一分发。

---

## 数据库

`prices_weekly` 表结构（已对齐 `prices` 表）：

```sql
CREATE TABLE prices_weekly (
  id         bigint(20)    NOT NULL AUTO_INCREMENT,
  ticker     varchar(20)   NOT NULL,
  date       date          NOT NULL,
  open       decimal(14,4) DEFAULT NULL,
  high       decimal(14,4) DEFAULT NULL,
  low        decimal(14,4) DEFAULT NULL,
  close      decimal(14,4) DEFAULT NULL,
  volume     bigint(20)    DEFAULT NULL,
  created_at timestamp     NOT NULL DEFAULT current_timestamp(),
  PRIMARY KEY (id),
  UNIQUE KEY uq_ticker_date (ticker, date),
  KEY idx_ticker (ticker),
  KEY idx_date (date)
)
```

`sync_log.data_type` ENUM 已包含 `'price_weekly'`（migration 002 已执行）。无需额外 DDL。

---

## 运行频率

每天触发（与日线 cron 并列）。tushare 周线仅周五收盘后有新数据，其他交易日增量检查后快速跳过。

---

## 不在范围内

- HK 周线
- 月线
- 周线指数价格
- `rebase` 子命令对 CN 周线的支持
