# CLI Task 2 Report — 旧入口 deprecation 转发

**Status:** DONE  
**Branch:** `feature/cli-consolidation`  
**Commit:** `fe70946c4d6980dce2b0584ed801faa40348700d`  
**Message:** `feat: 旧 CLI 入口 deprecation 转发至新二级命令`  
**Tests:** `uv run pytest tests/ -q` → **402 passed**

---

## 交付物

| 路径 | 说明 |
|------|------|
| `main.py` | 旧顶层入口调用 `warn_deprecated(old, new)` 后再 `cmd_*`；`futu` flush 失败文案改为 `futu flush` |
| `tests/test_cli.py` | 旧 help / deprecation stderr / 新路径无警告 |

`cli/deprecate.py` 未改（Task1 已提供 `warn_deprecated`）。

---

## 行为

**旧顶层（warn → cmd）：**

| old | new |
|-----|-----|
| `daily` | `prices daily` |
| `weekly` | `prices weekly` |
| `intraday` | `prices intraday` |
| `rebase` | `prices rebase` |
| `tushare-sync` | `tushare sync` |
| `tushare-full` | `tushare full` |
| `tushare-backfill` | `tushare sync` |
| `tushare-flush` | `tushare flush` |
| `futu-sync` | `futu sync` |
| `futu-full` | `futu full` |
| `futu-flush` | `futu flush` |
| `migrate-intraday` | `db migrate-intraday` |

**新路径** `prices/*` / `tushare/*` / `futu/*` / `db/*`：**无** deprecation。

警告格式（stderr）：

```text
[deprecated] `daily` → 请改用 `prices daily`（旧命令仍可用，将在后续版本移除）
```

## 测试新增

- `test_old_daily_help_still_works`
- `test_old_daily_emits_deprecation_on_run`
- `test_old_tushare_sync_emits_deprecation_on_run`
- `test_new_prices_daily_no_deprecation`
- `test_new_tushare_sync_no_deprecation`

## 未改

- `jobs/*` / `apis/*` 业务逻辑
- README / CLAUDE / `daily_update.sh`（Task4）
- 其余测试仍优先走旧命令（Task3）

## Concerns

1. **旧 CLI 测试仍走 deprecated 路径**（`test_futu_cli`、`test_main_tushare_backfill` 等）：stderr 会多一行警告，当前断言不读 stderr，故绿；Task3 改首选新路径后警告会从这些用例消失。
2. **`tushare-backfill` → `tushare sync`：** 语义上 backfill 带 `--start`，映射到 `tushare sync`（可带 `--start`）与 plan/spec 一致；用户若以为「sync 无 start」可能短暂困惑，docstring/README 应在 Task4 说清。
3. **flush 失败提示** 已统一为新二级命令（tushare Task1 已改；futu 本任务改为 `futu flush`）。
