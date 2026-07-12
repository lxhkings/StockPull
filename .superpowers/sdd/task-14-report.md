# Task 14 Report: CLAUDE/README 对齐 apis+jobs 架构

## Status
**PASS**

## Commit
- **Hash:** `fd850eb4bcd3a539f317ba848e852ff0dd7415a8` (short: `fd850eb`)
- **Branch:** `feature/api-centric-modularization`
- **Message:** `docs: CLAUDE/README 对齐 apis+jobs 架构`

## Files updated

| File | Change |
|------|--------|
| `CLAUDE.md` | 三家族 `data/ts_ingest/futu_ingest` → `apis/{yfinance,tushare,futu,static}` + `jobs/`；依赖方向表；扩展 checklist；MarketModule 在 `jobs/pipeline`；CN/HK `index` 忽略；`core.trading_calendar` / `modules.{index_base,price_write,sync_log}` |
| `README.md` | 架构树重写；HSI 路径 → `apis/static/hsi_constituents.csv`；`ts_ingest.*` import 示例与 FAQ 路径改为 `apis.tushare.*`；MarketModule 签名含 `index` 说明 |
| Design spec status（本地） | `docs/superpowers/specs/2026-07-12-api-centric-modularization-design.md` 状态改为 P0–P4 完成；**该路径在 `.gitignore`，未进 git** |

## Content highlights (CLAUDE)

- Dependency: `main → jobs/apis/core/modules`；`jobs` 禁 SDK；`apis` 禁 `jobs` 与跨子包互引
- Extension checklist: 同 API 新接口 / 新数据源 / 新市场
- `list_active_tickers(index)`: US 多指数；CN/HK ignore

## Verification
- `rg` on README/CLAUDE: no remaining `data/` pipeline paths, `ts_ingest/`, `futu_ingest/`, or `from db`
- Docs-only commit; tests re-run under Task 15

## Concerns
- Design spec under `docs/superpowers/` is gitignored — status line update is local-only unless ignore rules change.
- Historical design docs under `docs/superpowers/specs/*` still mention old paths (archive; not rewritten this task).
