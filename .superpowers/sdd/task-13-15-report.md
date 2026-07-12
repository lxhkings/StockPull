# Tasks 13–15 Combined Report (P4 收尾)

## Overall status
**PASS** — dependency inversion fixed; `data/` removed; docs aligned; full boundary suite + pytest green.

## Commits

| Order | Short | Full hash | Message |
|-------|-------|-----------|---------|
| 1 | `9fc2ce7` | `9fc2ce71c6829a3db1619fbc35e3bf6e467f17f6` | `fix: prices_intraday 不再依赖 jobs（用 modules.db_admin）` |
| 2 | `6506101` | `65061010ce4631052b2406cc7b9878ed24b8dd44` | `chore: 移除已搬空的 data 包` |
| 3 | `fd850eb` | `fd850eb4bcd3a539f317ba848e852ff0dd7415a8` | `docs: CLAUDE/README 对齐 apis+jobs 架构` |

Branch: `feature/api-centric-modularization`  
Parent of series: `14b4d16` (Task 12)

## Per-task

### Pre-fix + Task 13
- Intraday universe via `modules.db_admin.get_index_tickers` (SP500 ∪ R1000)
- `apis/` no longer imports `jobs`
- Empty `data/` package deleted (`git rm`)

### Task 14
- CLAUDE.md + README.md rewritten for `apis/*` + `jobs/*` + extension checklist
- CN/HK `list_active_tickers(index)` ignore documented
- Local design-spec status line updated (gitignored path)

### Task 15
- All §4.2 boundary rgs clean
- `394 passed, 3 skipped`

## Test summary
```
uv run pytest tests/ -q
======================== 394 passed, 3 skipped in ~4s ========================
```

## Remaining concerns
1. `scripts/*` probe tools still import `futu` SDK directly (out of jobs boundary).
2. Unused imports in `jobs/market_hk.py` (pre-existing).
3. `docs/superpowers/**` gitignored — design status not in repo history.
4. Smoke tests need NAS.

See also: `task-13-report.md`, `task-14-report.md`, `task-15-report.md`.
