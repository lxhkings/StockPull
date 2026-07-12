# Task 15 Report: 边界验收 + 全量测试

## Status
**PASS**

## Boundary suite

| # | Check | Result |
|---|--------|--------|
| 1 | `test -d jobs` | OK |
| 2 | `rg` SDK imports in `jobs/` | no hits |
| 3 | tushare / `ts.pro_bar` / `pro_api` outside `apis/tushare` (excl tests/docs/venv) | no hits |
| 4 | `import yfinance` / `yf.download` outside `apis/yfinance` (excl tests/docs/venv) | no hits |
| 5 | `from data.` / `import data.` in `*.py` | no hits |
| 6 | cross-`apis` imports under `apis/{yfinance,tushare,futu,static}` | **only same-package** imports |
| 7 | `from jobs` / `import jobs` under `apis/` | no hits |
| 8 | `data/` directory | gone |

No residual import cleanup commit required (suite clean).

## Full tests

```bash
uv run pytest tests/ -q
======================== 394 passed, 3 skipped in 4.00s ========================
```

| Metric | Value |
|--------|-------|
| Collected | 397 |
| Passed | 394 |
| Failed | 0 |
| Skipped | 3 (`test_db_smoke`) |

## Related commits (Tasks 13–15 + pre-fix)

| Hash (short) | Full | Message |
|--------------|------|---------|
| `9fc2ce7` | `9fc2ce71c6829a3db1619fbc35e3bf6e467f17f6` | `fix: prices_intraday 不再依赖 jobs（用 modules.db_admin）` |
| `6506101` | `65061010ce4631052b2406cc7b9878ed24b8dd44` | `chore: 移除已搬空的 data 包` |
| `fd850eb` | `fd850eb4bcd3a539f317ba848e852ff0dd7415a8` | `docs: CLAUDE/README 对齐 apis+jobs 架构` |

No extra `test: 边界验收与残留 import 清理` commit (nothing left to clean).

## Concerns / remaining notes
- **`scripts/probe_futu_limits.py` / `scripts/verify_futu_apis.py`** 直接 `from futu`：属探测脚本，不在 jobs 边界 rg 范围内；符合「SDK 仅 apis + 显式脚本」的实践，若日后收紧可再迁。
- **`jobs/market_hk.py`** 仍有未使用的 `get_conn`/`query` import（Task 12 已记；本轮未做无关清理）。
- Design/plan 在 `docs/superpowers/` 被 gitignore；CI 若要归档需另议。
- `test_db_smoke` 3 skipped：需 NAS 可达时才跑。
