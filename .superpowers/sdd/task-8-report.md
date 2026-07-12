# Task 8 Report: index_base → modules（C5）

## Status
**PASS**

## Commit
- **Hash:** `c534bac7d6899db9a0e8edb8ff3dee3d17e64193` (short: `c534bac`)
- **Branch:** `feature/api-centric-modularization`
- **Message:** `refactor: index_base 迁入 modules（C5，消除跨源共享写表歧义）`

## Move

| Old path | New path |
|----------|----------|
| `data/index_base.py` | `modules/index_base.py` |

## Import remaps

| Old | New |
|-----|-----|
| `from data.index_base import ...` | `from modules.index_base import ...` |
| `data.index_base` (patches) | `modules.index_base` |

### Call sites updated
- `ts_ingest/backfill_lists.py` — `register_stocks` + docstring path
- `ts_ingest/index_cn.py` — snapshot helpers
- `data/index_updater_us.py`
- `data/index_updater_hk.py`
- `data/index_updater_russell1000.py`
- `tests/test_index_base.py` — import + module docstring
- `CLAUDE.md` — architecture paths + modules 列表补全 `index_base.py` / `price_write.py`

## Rationale
`index_base` 含 `index_constituents` / `stocks` / `constituent_changes` / `index_sync_log` 等表语义写操作，属跨家族业务模块，应落在 `modules/`（非 `core/` 纯组件，也非某单一 API 源目录）。迁入后 `data/` 与 `ts_ingest/` 对写表辅助的依赖路径一致，消除「共享写表逻辑挂在 data 下」的跨源歧义。

## Verification

```bash
rg -n "data\.index_base|from data import index_base" -g'*.py' --glob '!**/.venv/**' --glob '!docs/**'
# no hits (exit 1)

rg -n "def register_stocks" -g'*.py' --glob '!**/.venv/**'
# only modules/index_base.py:117

uv run pytest tests/ -q
============================= 397 passed in 6.22s ==============================
```

| Metric | Value |
|--------|-------|
| Collected | 397 |
| Passed | 397 |
| Failed | 0 |
| Skipped | 0 |

## Concerns
- 无逻辑变更；纯路径迁移 + import 重写。
- Test 文件名仍为 `tests/test_index_base.py`（与模块名一致，无需改名）。
- README.md 若仍写 `data/index_base` 路径，本任务未改（docs 可走后续 doc 刷新）；CLAUDE.md 已同步。
