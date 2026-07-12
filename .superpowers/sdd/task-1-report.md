# Task 1 Report: Delete reconcile dead code

## Status
DONE

## Commit
`67e6edb284187db10666f6b6c772552e40aeeb97` (`67e6edb`)

## Branch
`feature/api-centric-modularization`

## Steps Completed

### 1. Verify zero business callers
```bash
rg -n "reconcile|RECONCILE_PRICE_TOLERANCE" -g'*.py' --glob '!**/.venv/**' --glob '!docs/**'
```

**Hits before deletion (expected only):**
| File | Role |
|------|------|
| `data/reconcile.py` | source (dead) |
| `tests/test_reconcile.py` | tests for dead source |
| `config.py` | `RECONCILE_PRICE_TOLERANCE` constant |

No callers in `main.py`, `data/pipeline.py`, market modules, or any other business path.

### 2. Remove source & tests
```bash
git rm data/reconcile.py tests/test_reconcile.py
```

### 3. Edit `config.py`
Deleted:
```python
# Reconcile tolerance for two-source comparison
RECONCILE_PRICE_TOLERANCE = 0.005   # 0.5%
```

### 4. Verify
```bash
rg -n "reconcile|RECONCILE_PRICE_TOLERANCE" -g'*.py' --glob '!**/.venv/**' --glob '!docs/**'
# → zero hits (rg exit 1)

uv run pytest tests/ -q
# → 380 passed in 2.85s
```

docs/ may still mention reconcile — ignored per task scope.

### 5. Commit
Message:
```
chore: 删除未接线的 reconcile 死码

零 main/pipeline 调用者；删源码、测试与 RECONCILE_PRICE_TOLERANCE。
```

## Diff Summary
- Deleted: `data/reconcile.py`
- Deleted: `tests/test_reconcile.py`
- Modified: `config.py` (removed `RECONCILE_PRICE_TOLERANCE` and comment)

## Behavior
Zero runtime behavior change: reconcile was never wired into main/pipeline.

## Concerns
None.
