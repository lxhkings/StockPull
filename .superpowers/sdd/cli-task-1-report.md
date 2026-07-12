# CLI Task 1 Report — parser 骨架 + 新旧分发

**Status:** DONE  
**Branch:** `feature/cli-consolidation`  
**Commit:** `981729e9c03f08b3ccaf0158c4d85a193019d128`  
**Message:** `feat: CLI 二级命令 prices/tushare/futu/db（旧入口 SUPPRESS 暂保留）`  
**Tests:** `uv run pytest tests/ -q` → **397 passed**

---

## 交付物

| 路径 | 说明 |
|------|------|
| `cli/__init__.py` | 包入口（最小 docstring） |
| `cli/deprecate.py` | `warn_deprecated(old, new)`（Task1 未接线，供 Task2） |
| `cli/parser.py` | `build_parser()`：新二级树 + 旧顶层 `help=SUPPRESS` |
| `main.py` | 用 `build_parser`；新/旧分发；删死代码；flush 文案；docstring |
| `tests/test_cli.py` | help 断言改为新顶层（见 Concerns） |

## main.py 行为

- **新路径：** `prices {daily,weekly,intraday,rebase}` / `tushare {sync,full,flush}` / `futu {sync,full,flush}` / `db migrate-intraday` / `init` / `status`
- **旧路径：** 全部仍可解析并直调 `cmd_*`，**无 deprecation warn**（Task2）
- **dest：** `prices_cmd` / `tushare_cmd` / `futu_cmd` / `db_cmd`
- **`tushare sync`：** 带 `--start`，分发 `cmd_tushare_backfill(..., start=args.start)`
- **死代码：** `cmd_tushare_sync` 不可达 `return 0` 已删
- **文案：** flush 失败提示 `tushare-flush` → `tushare flush`
- **docstring：** `StockPull CLI: prices | tushare | futu | init | status | db`

## 未改

- `jobs/*` / `apis/*` 业务逻辑
- deprecation 接线（Task2）
- 其余测试路径仍走旧命令（Task3 再改首选新路径）
- README / CLAUDE / `daily_update.sh`（Task4）

## Concerns

1. **argparse SUPPRESS 坑：** CPython 3.12 对 subparser `help=SUPPRESS` 会在 help 列表显示字面 `==SUPPRESS==`。实现用 `_hide_suppressed()` 过滤 `_choices_actions`，并用 `metavar="{prices,tushare,futu,init,status,db}"` 收紧 usage 行。
2. **test_cli help 断言：** 原测试要求一级 help 含 `daily`/`rebase`；与 SUPPRESS 冲突。Task1 最小改 `test_help_shows_subcommands` 为新顶层 + 断言旧名不出现。Task3 可继续补 `prices daily -h` 等 smoke。
3. **`futu-flush` 失败提示** 仍写旧命令 `futu-flush`（任务仅要求改 tushare 侧）；Task2/4 可一并统一为 `futu flush`。
4. **`MARKETS` 仍在 `main.py` 导出**；parser 内另有同名常量，避免循环依赖。
