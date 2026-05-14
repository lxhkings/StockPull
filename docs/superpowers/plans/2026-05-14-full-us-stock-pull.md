# 全量美股日线拉取 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修改 `daily --market us` 默认拉取全部美股（5927支），新增 `--index SP500` 参数限制为指数成分股。

**Architecture:** 修改 `market_us.py` 的 `list_active_tickers()` 返回 stocks 表全部 US ticker，保持 Protocol 签名兼容。`main.py` 新增 `--index` 参数传递到 Pipeline。

**Tech Stack:** Python 3.12, yfinance API, MariaDB, argparse

---

## File Structure

| 文件 | 改动 |
|------|------|
| `data/market_us.py` | `list_active_tickers(index=None)` 返回全部或 SP500 |
| `main.py` | daily/rebase 新增 `--index` 参数 |
| `data/pipeline.py` | `Pipeline.daily(index=None)` 支持参数传递 |
| `README.md` | 更新文档说明 |

---

### Task 1: 修改 market_us.py 的 list_active_tickers

**Files:**
- Modify: `data/market_us.py:38-39`

- [ ] **Step 1: 修改 list_active_tickers 函数签名和实现**

```python
def list_active_tickers(index: Optional[str] = None) -> list[str]:
    """返回美股 ticker 列表。index=None 全量，index='SP500' 指数成分股。"""
    if index == "SP500":
        return get_index_tickers("SP500")
    rows = query("SELECT ticker FROM stocks WHERE exchange='US' ORDER BY ticker")
    return [r["ticker"] for r in rows]
```

- [ ] **Step 2: 修改 rebase 函数调用**

```python
def rebase(tickers: Optional[list[str]] = None, years: Optional[int] = None, index: Optional[str] = None) -> dict[str, str]:
    """US rebase: full re-pull from specified years (raw prices, no hfq)."""
    targets = tickers if tickers else list_active_tickers(index=index)
    return stock_updater_us.update_prices_batch(targets, full_rebase=True, years=years)
```

- [ ] **Step 3: 语法检查**

Run: `uv run python -m py_compile data/market_us.py`
Expected: 无错误

- [ ] **Step 4: Commit**

```bash
git add data/market_us.py
git commit -m "feat: list_active_tickers 支持全量美股或 SP500 成分股"
```

---

### Task 2: 修改 pipeline.py 支持 index 参数

**Files:**
- Modify: `data/pipeline.py:41-57`

- [ ] **Step 1: 修改 Pipeline.daily 方法签名**

```python
def daily(self, index: Optional[str] = None) -> None:
    mid = self.m.market_id
    log.info(f"[{mid}] === Step 1: update index constituents ===")
    new_tickers, inserted, removed = self.m.update_index()
    log.info(f"[{mid}] index: +{len(new_tickers)} new, {inserted} rows in snapshot, -{removed} removed")

    if new_tickers:
        log.info(f"[{mid}] === Step 2: backfill {len(new_tickers)} new tickers ===")
        self.m.backfill_new(new_tickers)

    log.info(f"[{mid}] === Step 3: incremental update ===")
    # US 模块支持 index 参数，CN/HK 不支持（使用默认调用）
    if hasattr(self.m, 'list_active_tickers'):
        import inspect
        sig = inspect.signature(self.m.list_active_tickers)
        if 'index' in sig.parameters:
            all_tickers = self.m.list_active_tickers(index=index)
        else:
            all_tickers = self.m.list_active_tickers()
    else:
        all_tickers = self.m.list_active_tickers()
    self.m.incremental(all_tickers)

    log.info(f"[{mid}] === Step 4: update index price ===")
    rows = self.m.update_index_price()
    log.info(f"[{mid}] index price: +{rows} rows")
    log.info(f"[{mid}] === pipeline complete ===")
```

- [ ] **Step 2: 语法检查**

Run: `uv run python -m py_compile data/pipeline.py`
Expected: 无错误

- [ ] **Step 3: Commit**

```bash
git add data/pipeline.py
git commit -m "feat: Pipeline.daily 支持 index 参数传递"
```

---

### Task 3: 修改 main.py 添加 --index 参数

**Files:**
- Modify: `main.py:34-37` (daily 参数)
- Modify: `main.py:39-42` (rebase 参数)
- Modify: `main.py:87-92` (cmd_daily 调用)
- Modify: `main.py:96-104` (cmd_rebase 调用)
- Modify: `main.py:133-134` (args 处理)

- [ ] **Step 1: 添加 --index 参数到 daily 命令**

```python
p_daily.add_argument("--market", choices=MARKETS, default="all")
p_daily.add_argument("--code", action="append", default=None,
                     help="Only this ticker (repeatable, debug aid)")
p_daily.add_argument("--index", default=None,
                     help="指数成分股（仅 US 市场：SP500）")
```

- [ ] **Step 2: 添加 --index 参数到 rebase 命令**

```python
p_rebase.add_argument("--market", choices=("cn", "hk", "us"), required=True)
p_rebase.add_argument("--code", action="append", default=None)
p_rebase.add_argument("--years", type=int, default=None, help="历史年数（默认：US=5, CN/HK=15）")
p_rebase.add_argument("--index", default=None,
                      help="指数成分股（仅 US 市场：SP500）")
```

- [ ] **Step 3: 修改 cmd_daily 函数签名和调用**

```python
def cmd_daily(market: str, codes: list[str] | None, index: str | None) -> int:
    from data.pipeline import Pipeline
    targets = ["us", "cn", "hk"] if market == "all" else [market]
    for m in targets:
        try:
            mod = _import_market(m)
        except ImportError as e:
            print(f"[{m}] not yet implemented: {e}", file=sys.stderr)
            continue

        if codes:
            # Single-ticker debug path: skip Step 1/2, run incremental on the codes only
            print(f"[{m}] daily --code {codes}: running incremental only")
            mod.incremental(codes)
        else:
            # 只对 US 市场传递 index 参数
            pipe_index = index if m == "us" else None
            Pipeline(mod).daily(index=pipe_index)
    return 0
```

- [ ] **Step 4: 修改 cmd_rebase 函数签名和调用**

```python
def cmd_rebase(market: str, codes: list[str] | None, years: int | None, index: str | None) -> int:
    mod = _import_market(market)
    if not hasattr(mod, "rebase"):
        print(f"[{market}] rebase not implemented", file=sys.stderr)
        return 1
    # 只对 US 市场传递 index 参数
    rebase_index = index if market == "us" else None
    targets = codes or mod.list_active_tickers(index=rebase_index)
    years_msg = f" ({years} 年)" if years else ""
    index_msg = f" [{index}]" if index else ""
    print(f"[{market}] rebase {len(targets)} tickers{index_msg}{years_msg} (full history)")
    mod.rebase(targets, years=years, index=rebase_index)
    return 0
```

- [ ] **Step 5: 修改 args 处理**

```python
if args.cmd == "daily":
    return cmd_daily(args.market, args.code, args.index)
if args.cmd == "rebase":
    return cmd_rebase(args.market, args.code, args.years, args.index)
```

- [ ] **Step 6: 语法检查**

Run: `uv run python -m py_compile main.py`
Expected: 无错误

- [ ] **Step 7: Commit**

```bash
git add main.py
git commit -m "feat: daily/rebase 新增 --index 参数支持 SP500 成分股"
```

---

### Task 4: 更新 README.md 文档

**Files:**
- Modify: `README.md:28-42`

- [ ] **Step 1: 更新 daily 命令说明**

```markdown
# 日常增量同步
uv run main.py daily --market us   # 美股全部（5927支）
uv run main.py daily --market us --index SP500  # 仅 SP500 成分股
uv run main.py daily --market cn   # A股
uv run main.py daily --market hk   # 港股
uv run main.py daily               # 全市场（默认）
```

- [ ] **Step 2: 更新 rebase 命令说明**

```markdown
# 全量回补（hfq 漂移修复）
uv run main.py rebase --market cn  # A股全量重拉（tushare hfq，默认15年）
uv run main.py rebase --market hk  # 港股全量重拉（yfinance hfq，默认15年）
uv run main.py rebase --market us  # 美股全量重拉（yfinance raw，默认5年，5927支）
uv run main.py rebase --market us --index SP500  # 仅 SP500 成分股
uv run main.py rebase --market us --years 10  # 指定10年历史
uv run main.py rebase --market cn --code 600519.SH  # 单只股票全量重拉
```

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: 更新美股全量拉取说明"
```

---

### Task 5: 测试验证

**Files:**
- Test: `uv run main.py daily --market us --index SP500`
- Test: `uv run main.py rebase --market us --years 1 --index SP500`

- [ ] **Step 1: 测试 SP500 成分股拉取**

Run: `uv run main.py daily --market us --index SP500`
Expected: 日志显示拉取 SP500 成分股（约500支）

- [ ] **Step 2: 测试全量美股（小范围）**

Run: `uv run main.py rebase --market us --years 1 --code AAPL`
Expected: 日志显示拉取 1 支股票 1年历史

- [ ] **Step 3: 检查 prices 表数据**

Run: `uv run main.py status`
Expected: 显示美股同步状态

---

## Verification Summary

1. `daily --market us` 拉全部美股（stocks 表 exchange='US'）
2. `daily --market us --index SP500` 拉成分股（index_constituents 表）
3. `rebase --market us --index SP500` 全量重拉成分股
4. README.md 文档清晰说明用法