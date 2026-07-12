# CLI Task 3 Report — 测试改首选新命令

**Status:** DONE  
**Branch:** `feature/cli-consolidation`  
**Commit:** `ebe657171895e3ebe5e7db93e02dda034d2e66b2`  
**Message:** `test: CLI 测试改用 prices/tushare/futu 二级命令`  
**Tests:** `uv run pytest tests/ -q` → **406 passed**

---

## 交付物

| 路径 | 变更 |
|------|------|
| `tests/test_cli.py` | 补 `prices daily --help` / `tushare sync --help` / `prices` 无子命令失败；保留旧 deprecation smoke |
| `tests/test_cli_rebase_etf.py` | `prices rebase --market cn --etf-only` |
| `tests/test_futu_cli.py` | 主路径 `futu full` / `futu sync`；保留 1 例 `futu-full` + deprecation 断言 |
| `tests/test_main_tushare_backfill.py` | CLI 分发改 `tushare full` / `tushare sync`；`cmd_*` 单测未动 |

---

## 测试策略

**首选新路径：**

| 场景 | 调用 |
|------|------|
| 日线 | `prices daily` |
| rebase ETF | `prices rebase --etf-only` |
| tushare full/sync | `tushare full` / `tushare sync` |
| futu full/sync | `futu full` / `futu sync` |

**旧入口 smoke（保留）：**

- `daily --help` / `daily` deprecation
- `tushare-sync` deprecation
- `daily --market europe` 参数校验
- `futu-full` 仍 `force=True` + deprecation

**注意：** 新路径 `tushare sync` 分发到 `cmd_tushare_backfill(..., start=None)`，不再走 `cmd_tushare_sync`；CLI 断言已对齐。

---

## 未改

- `tests/test_intraday_updater_us.py` 仍走顶层 `intraday`（本 Task 范围外；旧路径仍可用）
- README / CLAUDE / `daily_update.sh`（Task4）
- 业务 `cmd_*` / `apis/*` / `jobs/*`

## Concerns

1. **intraday CLI 测试仍走 deprecated 路径**（`test_intraday_updater_us.py`）：stderr 会有警告，断言不读 stderr，故绿。后续可改为 `prices intraday`。
2. **旧 `tushare-sync` vs 新 `tushare sync` 分发目标不同**（`cmd_tushare_sync` vs `cmd_tushare_backfill`）：语义等价（start=None），但 patch 目标不同——已在本 Task 修正。
3. Task4 文档/cron 尚未切新命令。
