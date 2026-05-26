# CN 行业 ETF 日线采集 — 设计文档

**日期**: 2026-05-26
**目标**: 采集 A 股行业 ETF 后复权日线数据，与 US 行业 ETF（XL*）形成跨市场横向趋势对比能力。

## 背景

项目已有 US 11 个 GICS 行业 ETF（XLK/XLY/XLF/...）+ QQQ 日线数据，存 `index_prices` 表，via yfinance。

CN 侧目前仅 CSI800 综合指数 via tushare `index_daily`。缺行业维度数据，无法做"中美同行业趋势对比"分析（例如对比 A 股银行 ETF vs US 金融 XLF）。

## 范围

**纳入**：
- A 股行业 ETF 后复权日线（close）
- 按 GICS 11 类对齐 + A 股特色主题 ETF，共约 17 只
- 复用 `index_prices` 表存储，index_id 用 ts_code

**不纳入**：
- ETF 成分股（与 CSI800 模式相同，仅价格不拉成分）
- 分钟级数据
- OHLCV 全量（仅 close）

## ETF 清单

按 GICS 11 大类对齐 US XL*，覆盖完整 + A 股热门主题：

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

⚠️ 部分 ts_code 需通过 tushare `fund_basic` 验证存在性（实施第一步）。

## 数据源

- **fund_daily**: ETF 日线 raw close
- **fund_adj**: 复权因子（adj_factor）

复权公式：`hfq_close(t) = raw_close(t) × adj_factor(t)`

tushare 复权因子已归一化（与 `pro_bar adj='hfq'` 等价），无需除以 latest_factor。

ETF 无 `pro_bar` 接口，须手动合并 `fund_daily × fund_adj`。

## 架构

### 文件结构

| 文件 | 改动 | 估算行数 |
|---|---|---|
| `data/etf_updater_cn.py` | 新增 | ~80 |
| `config.py` | 增 `CN_SECTOR_ETFS` 字典 | ~25 |
| `data/market_cn.py` | `update_index_price()` 末尾调 `update_etf_prices()` | ~3 |
| `main.py` | `rebase` 加 `--etf-only` 参数 + 分支 | ~15 |
| `tests/test_etf_updater_cn.py` | 新增 | ~150 |
| `tests/test_config.py` | 补 1 case | ~5 |
| `README.md` | 增段落 | ~20 |
| `scripts/verify_cn_etfs.py` | 一次性验证 ts_code | ~15 |

### 数据流

```
uv run main.py daily --market cn
  ↓ cmd_daily()
  ↓ Pipeline.run()
  ↓ market_cn.update_index_price()
      ├─ CSI800 via tushare index_daily          (现有)
      └─ etf_updater_cn.update_etf_prices()      (新增)
            └─ for each ETF in CN_SECTOR_ETFS:
                 fund_daily(ts_code, start_date)
                 fund_adj(ts_code, start_date)
                 merge on trade_date → hfq_close
                 INSERT IGNORE index_prices
```

### 核心函数

`data/etf_updater_cn.py`:

```python
def fetch_etf_daily_hfq(ts_code: str, start_date: str | None) -> pd.DataFrame:
    """返回 DataFrame[date, hfq_close]，按 trade_date 合并 fund_daily × fund_adj。"""
    daily = client.call("fund_daily", ts_code=ts_code, start_date=start_date)
    adj   = client.call("fund_adj",   ts_code=ts_code, start_date=start_date)
    if daily.empty:
        return pd.DataFrame()
    if adj.empty:
        df = daily[["trade_date", "close"]].copy()
        df["hfq_close"] = df["close"]
        log.warning(f"[{ts_code}] fund_adj 空，使用 raw close")
    else:
        df = daily.merge(adj[["trade_date", "adj_factor"]], on="trade_date", how="left")
        df["adj_factor"] = df["adj_factor"].ffill().fillna(1.0)
        df["hfq_close"] = df["close"] * df["adj_factor"]
    df["date"] = pd.to_datetime(df["trade_date"]).dt.date
    return df[["date", "hfq_close"]].sort_values("date")


def update_etf_prices(full_rebase: bool = False) -> int:
    """遍历 CN_SECTOR_ETFS，增量或全量写入 index_prices。"""
    total = 0
    for ts_code, meta in CN_SECTOR_ETFS.items():
        try:
            if full_rebase:
                last_date = None
                start = "20100101"
            else:
                last = query("SELECT MAX(date) AS d FROM index_prices WHERE index_id=%s", (ts_code,))
                last_date = last[0]["d"] if last and last[0]["d"] else None
                start = last_date.strftime("%Y%m%d") if last_date else "20100101"

            df = fetch_etf_daily_hfq(ts_code, start_date=start)
            if last_date:
                df = df[df["date"] > last_date]
            if df.empty:
                continue

            rows = [(r.date, ts_code, to_float(r.hfq_close)) for r in df.itertuples(index=False)]
            n = execute(
                "INSERT IGNORE INTO index_prices (date, index_id, close) VALUES (%s,%s,%s)",
                rows, many=True,
            )
            total += n
            log.info(f"[{ts_code}] {meta['name']} 写入 {n} 行")
        except Exception as e:
            log.error(f"[{ts_code}] 失败: {e}")
            continue
    return total
```

### 配置

`config.py`:

```python
CN_SECTOR_ETFS = {
    "515220.SH": {"name": "煤炭ETF",     "gics": "Energy"},
    "512400.SH": {"name": "有色金属ETF", "gics": "Materials"},
    "512660.SH": {"name": "军工ETF",     "gics": "Industrials"},
    "159996.SZ": {"name": "家电ETF",     "gics": "ConsumerDiscretionary"},
    "512690.SH": {"name": "酒ETF",       "gics": "ConsumerStaples"},
    "512170.SH": {"name": "医疗ETF",     "gics": "HealthCare"},
    "512010.SH": {"name": "医药ETF",     "gics": "HealthCare"},
    "512800.SH": {"name": "银行ETF",     "gics": "Financials"},
    "512000.SH": {"name": "券商ETF",     "gics": "Financials"},
    "512720.SH": {"name": "计算机ETF",   "gics": "InformationTechnology"},
    "512480.SH": {"name": "半导体ETF",   "gics": "InformationTechnology"},
    "515050.SH": {"name": "5G通信ETF",   "gics": "CommunicationServices"},
    "159611.SZ": {"name": "电力ETF",     "gics": "Utilities"},
    "512200.SH": {"name": "房地产ETF",   "gics": "RealEstate"},
    "515790.SH": {"name": "光伏ETF",     "gics": "Theme.Solar"},
    "515030.SH": {"name": "新能源车ETF", "gics": "Theme.NEV"},
    "159995.SZ": {"name": "芯片ETF",     "gics": "Theme.Chip"},
}
```

### `market_cn.update_index_price()` 钩入

```python
def update_index_price() -> int:
    total = 0
    # ... 现有 CSI800 逻辑 ...
    total += csi800_inserted

    from data.etf_updater_cn import update_etf_prices
    total += update_etf_prices()
    return total
```

## CLI

无新增子命令——`daily --market cn` 自动包含 ETF。

`rebase` 子命令扩展：

```bash
uv run main.py rebase --market cn --etf-only   # 仅重灌 ETF
uv run main.py rebase --market cn              # 个股 + ETF 全量
```

`--etf-only` 内部调 `update_etf_prices(full_rebase=True)`。

## 复权重算策略

| 模式 | 行为 |
|---|---|
| 日常 daily | 增量追加（last_date 之后） |
| rebase --etf-only | 全量重灌（解决 ETF 分红/拆分历史 adj_factor 变化） |

日常增量在 ETF 分红日会出现微跳水（adj_factor 变化未传导至历史行），建议季度跑一次 rebase 修正。

## 测试矩阵

`tests/test_etf_updater_cn.py`:

| 用例 | 验证点 |
|---|---|
| `test_fetch_etf_daily_hfq_merges_close_and_adj` | mock fund_daily + fund_adj，hfq_close = close × adj_factor |
| `test_fetch_etf_daily_hfq_handles_missing_adj` | fund_adj 空 DataFrame → fallback raw close + warn |
| `test_fetch_etf_daily_hfq_ffill_adj_gaps` | adj_factor 缺日期用 ffill |
| `test_fetch_etf_daily_hfq_empty_when_no_daily` | fund_daily 空 → 返回空 DF |
| `test_update_etf_prices_incremental_skips_existing` | last_date 之后才写入 |
| `test_update_etf_prices_full_rebase_starts_from_2010` | full_rebase=True 忽略 last_date |
| `test_update_etf_prices_continues_on_single_failure` | 单 ETF API 抛错不阻断其他 |
| `test_update_etf_prices_writes_to_index_prices` | 写入 index_id=ts_code, close=hfq_close |

`tests/test_config.py`:
- `test_cn_sector_etfs_covers_gics_11` —— 字典含 GICS 11 类至少各一只

## 一次性验证脚本

`scripts/verify_cn_etfs.py`（实施第一步跑，跑完可删）：

```python
"""验证 CN_SECTOR_ETFS 中所有 ts_code 在 tushare fund_basic 存在。"""
from config import CN_SECTOR_ETFS
from ts_ingest.client import get_client

client = get_client()
codes = list(CN_SECTOR_ETFS.keys())
basic = client.call("fund_basic", market="E")
existing = set(basic["ts_code"].values)
missing = [c for c in codes if c not in existing]
if missing:
    print(f"MISSING: {missing}")
else:
    print(f"OK: 全部 {len(codes)} 只 ETF 存在")
```

## README 更新

新增段落：

```markdown
### CN 行业 ETF 数据

A股行业 ETF 后复权日线，存 `index_prices` 表，index_id 为 ts_code（如 `512800.SH`）。

清单：见 `config.CN_SECTOR_ETFS`（GICS 11 类对齐 + A 股主题，共 ~17 只）

# 查 GICS 行业 ETF 横向对比（CN vs US 同行业）
SELECT date, index_id, close
FROM index_prices
WHERE index_id IN ('512800.SH', 'XLF')  -- 银行 vs 美国金融
  AND date >= '2026-01-01'
ORDER BY date, index_id;

# 按 GICS 分类查 CN 行业 ETF
SELECT date, index_id, close
FROM index_prices
WHERE index_id IN ('512170.SH', '512010.SH')  -- 医疗 + 医药
ORDER BY date;
```

## 错误处理

- 单 ETF 失败不阻断其他（try/except per ticker）
- 失败 log error，不抛
- 与现有 CSI800 模式一致

## 验收

1. `uv run pytest tests/test_etf_updater_cn.py -v` 全绿
2. `uv run python scripts/verify_cn_etfs.py` 输出 OK
3. `uv run main.py daily --market cn` 日志可见各 ETF 写入行数
4. SQL 查 `index_prices` 含全部 ts_code 历史数据
5. `uv run main.py rebase --market cn --etf-only` 重灌成功
