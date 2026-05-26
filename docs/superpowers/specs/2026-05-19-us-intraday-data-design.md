# 美股分钟级行情数据（15m / 1h）设计文档

**日期：** 2026-05-19  
**范围：** 美股 SP500 + Russell1000（~1016 只）  
**数据源：** yfinance 免费 tier  

---

## 1. 目标

为量化策略回测提供美股分钟级历史行情，支持 15 分钟和 1 小时两个 interval，每日增量追加，长期积累完整历史。

---

## 2. 数据源限制

| interval | yfinance 可拉历史上限 |
|----------|---------------------|
| 15m      | 60 天               |
| 60m      | 730 天（2 年）       |

超出上限的历史通过每日增量追加方式随时间累积。

---

## 3. 存储设计

### 新表：`prices_intraday`

```sql
CREATE TABLE prices_intraday (
    ticker    VARCHAR(20)   NOT NULL,
    interval  VARCHAR(4)    NOT NULL,  -- '15m' 或 '60m'
    datetime  DATETIME      NOT NULL,
    open      DECIMAL(12,4),
    high      DECIMAL(12,4),
    low       DECIMAL(12,4),
    close     DECIMAL(12,4),
    volume    BIGINT,
    PRIMARY KEY (ticker, interval, datetime),
    INDEX idx_interval_ticker (interval, ticker, datetime)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### sync_log 复用

现有 `sync_log` 表新增两种 `data_type`：

| data_type      | 含义                  |
|----------------|-----------------------|
| `intraday_15m` | ticker 的 15m 最后同步时间 |
| `intraday_60m` | ticker 的 1h 最后同步时间  |

### 数据量估算

| interval | 初始拉取     | 年增量      |
|----------|------------|------------|
| 15m      | ~1.6M 行   | ~6.6M 行   |
| 1h       | ~5.2M 行   | ~1.8M 行   |
| **合计** | **~6.8M 行 ≈ 410MB** | **~8.4M 行/年** |

---

## 4. 模块结构

### 新文件

```
data/intraday_updater_us.py
```

### 修改文件

```
main.py          — 新增 intraday CLI 命令
db.py            — 建表 DDL（或单独迁移脚本）
```

---

## 5. 数据流

```
main.py intraday [--interval 15m|1h]
  └── intraday_updater_us.update_intraday(interval)
        ├── market_us.list_active_tickers() 取 ~1016 只
        ├── 按批（YF_BATCH_SIZE=40）循环
        │   ├── 查 sync_log 得各 ticker last_sync
        │   ├── 计算 start_date（max(last_sync+1bar, 可拉历史上限)）
        │   ├── yf.download(batch, interval='15m'|'60m', start=..., end=...)
        │   ├── 解析 MultiIndex DataFrame → (ticker, interval, datetime, OHLCV)
        │   ├── INSERT IGNORE → prices_intraday
        │   └── set_sync_ok / set_sync_error → sync_log
        └── 批次间等待 YF_BATCH_DELAY_BASE ± JITTER 秒
```

---

## 6. 增量窗口逻辑

- 首次拉取（sync_log 无记录）：从历史上限起点拉取全量
  - 15m：`today - 60 days`
  - 1h：`today - 730 days`
- 后续增量：从 `last_sync_date + 1 bar` 到当前时间
- `INSERT IGNORE` 保证幂等，重复运行安全

---

## 7. CLI

```bash
uv run main.py intraday                  # 15m 和 1h 均跑
uv run main.py intraday --interval 15m   # 仅 15m
uv run main.py intraday --interval 1h    # 仅 1h
```

---

## 8. 不在范围内

- Cron / 自动调度（手动触发）
- 其他 interval（1m、2m、5m、30m）
- 港股、A 股分钟数据
- 数据清洗 / 异常值处理
