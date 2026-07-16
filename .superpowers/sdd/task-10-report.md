# Task 10 Report: 文档与 design 状态 + 终验

## Status

**Done.** README 架构树补全 `cli/` 与 batch/write_utils；design 标为已实现；CLAUDE 主轴/依赖表补 `cli/`；终验全绿。

## Changes

| File | Change |
|------|--------|
| `README.md` | 架构树：`main.py` 薄入口说明；`cli/*`；`prices_batch.py` / `prices_cn_batch.py` / `write_utils.py` |
| `docs/superpowers/specs/2026-07-16-structural-debt-cleanup-design.md` | 状态 → `已实现（P0–P4）— 完成日 2026-07-16` |
| `CLAUDE.md` | 主轴加 `cli/`；依赖方向加 `cli/*`；扩展表加 `cli/` 行 |
| `main.py` | 删除未使用 `log = logging.getLogger(__name__)`（Task 9 nit） |

## Final verification

```bash
uv run pytest tests/ -q
→ 448 passed in 2.84s

rg -n 'AKSHARE_|to_akshare|to_efinance' --type py
→ 仅 main.py `_AKSHARE_NO_PROXY` 变量名（允许）

rg -n 'def update_prices_batch|def update_weekly_batch' apis/
→ prices_us / prices_hk / prices_cn / prices_us_weekly / prices_cn_weekly（日/周双入口仍在）

rg -n 'ON DUPLICATE KEY UPDATE' apis/futu/
→ 实际 SQL 仅 write_utils.py；其余为注释 + 调用 upsert_rows
```

## Self-review (plan vs spec)

| Spec 项 | 结果 |
|---------|------|
| P0–P4 实现 | 既有 Task 1–9 |
| 文档 + design 状态 | 本 Task |
| 不做跨源引擎 / hk / etf… | 未越界 |

## Commit

`docs: mark structural debt cleanup P0–P4 implemented`
