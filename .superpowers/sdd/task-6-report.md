# Task 6 Report: C4 remove inspect.signature reflection

## Status
**PASS**

## Commit
- **Hash:** `6c366ffc2bc13206e9573ec9e4973e33d0f03dab` (short: `6c366ff`)
- **Branch:** `feature/api-centric-modularization`
- **Message:** `refactor: MarketModule 统一 index 参数，去掉 inspect 反射`
- **Files (5):**
  - `data/pipeline.py`
  - `data/market_cn.py`
  - `data/market_hk.py`
  - `main.py`
  - `tests/test_pipeline_intraday.py`

## Changes

| Item | Action |
|------|--------|
| `MarketModule.list_active_tickers` | Protocol now `list_active_tickers(self, index: str \| None = None) -> list[str]` |
| `Pipeline.daily()` | Always `all_tickers = self.m.list_active_tickers(index=index)`; drop `import inspect` + signature branch |
| `market_cn.list_active_tickers` / `rebase` | Accept `index: str \| None = None`, ignore it; docstring states single-universe |
| `market_hk.list_active_tickers` / `rebase` | Same as CN |
| `market_us` | Unchanged — already uses `index` for SP500/RUSSELL1000 |
| `main.cmd_rebase` | Always `list_active_tickers(index=index)` and `rebase(..., index=index)`; remove local `inspect` |

## Verification

```bash
rg -n "inspect.signature" main.py data/pipeline.py
# no hits (rg exit 1)

uv run pytest tests/ -q
============================= 397 passed in 3.85s ==============================
```

| Metric | Value |
|--------|-------|
| Collected | 397 |
| Passed | 397 |
| Failed | 0 |
| Skipped | 0 |

## Concerns
- CN/HK `rebase(index=...)` accepts and ignores `index`; if targets are pre-resolved by caller, behavior is identical. Fallback `list_active_tickers()` inside rebase still ignores index when `tickers` is None — same as before for CN/HK.
- `tests/test_pipeline_intraday.py` mock modules updated to accept `index=` so they match the unified Protocol call site.
- Other `inspect` usage remains in `tests/test_us_index_price.py` (unrelated to MarketModule reflection).
