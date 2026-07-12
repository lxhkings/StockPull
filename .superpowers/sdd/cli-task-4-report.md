# CLI Task 4 Report — 文档与 daily_update.sh 收敛

**Status:** DONE  
**Branch:** `feature/cli-consolidation`  
**Commit:** `6a2fab36ec70c6ed3c1892d7be78526b266a82a9`  
**Message:** `docs: CLI 收敛文档与 daily_update.sh 改用 prices daily`  
**Tests:** `uv run pytest tests/test_cli.py -q` → **11 passed**（文档/脚本任务，未全量跑）

---

## 交付物

| 路径 | 变更 |
|------|------|
| `scripts/daily_update.sh` | `python -m main daily $MARKETS` → `prices daily --market <m>`；多市场循环；`set +e` 捕获退出码 |
| `README.md` | 全部用户向 CLI 示例改为二级命令；新增「旧命令映射」表；FAQ/数据源文案同步 |
| `CLAUDE.md` | Commands 区块改为 `prices`/`tushare`/`futu`/`db` 新路径 |

## daily_update.sh 行为

```text
无参数 / all  →  prices daily --market all
us cn         →  依次 prices daily --market us / --market cn
```

- 日志头尾保留：`==== daily_update … ====` / `==== done ====` / `==== FAILED … ====`
- `set -e` 与退出码：在 `run_one` 循环外包一层 `set +e`，避免中途 abort 或拿不到 `EXIT_CODE`；多市场时任一失败保留最后一个非零码
- Usage 注释更新为新 CLI

## README 映射表

| 旧 | 新 |
|----|-----|
| daily/weekly/intraday/rebase | prices … |
| tushare-sync/full/flush | tushare sync/full/flush |
| tushare-backfill | tushare sync（`--start` 自定义起点） |
| futu-sync/full/flush | futu sync/full/flush |
| migrate-intraday | db migrate-intraday |

## 未改

- `jobs/*` / `apis/*` / `main.py` / `cli/*` / tests
- 架构章节中的 protocol 方法名（`rebase()`/`weekly()` 等）与表名/scope 名（非用户 CLI）

## Concerns

1. **多市场退出码语义：** 多参数循环保留最后一个非零 exit code（非“任一失败即停”）；与旧脚本“单次调用一个 daily $MARKETS”不同——旧实现里 `daily us hk` 若旧 CLI 不接受位置参数可能本就不对；新行为与任务给定 `run_one` 循环一致。
2. **`tushare-backfill` 文档消失：** 用户面只写 `tushare sync --start`；旧入口仍可用（deprecation），映射表已说明。
3. **全量 pytest 未跑：** 仅 `test_cli.py`；本任务无代码路径变更，风险低。
4. **cron 用户须依赖本脚本或自行改命令：** 若有外部 cron 直接调 `python -m main daily`，仍会 deprecation 警告但功能可用。
