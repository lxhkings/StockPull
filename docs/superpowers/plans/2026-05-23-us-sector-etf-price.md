# US Sector ETF Price Collection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add 11 US sector ETF daily price collection to existing `daily --market us` pipeline.

**Architecture:** Extend `update_index_price()` indices list with hardcoded ETF tickers. No database schema changes, no new tables.

**Tech Stack:** Python, yfinance, MariaDB

---

## File Structure

**Files modified:**
- `data/market_us.py:94-96` — extend `indices` list in `update_index_price()`

**Files created:**
- `tests/test_us_index_price.py` — verify ETF list in indices

---

### Task 1: Write ETF list verification test

**Files:**
- Create: `tests/test_us_index_price.py`

- [ ] **Step 1: Write the failing test**

```python
"""Tests for US market index/ETF price fetching."""
import pytest
from unittest.mock import patch, MagicMock
import pandas as pd
from datetime import date


def test_update_index_price_includes_sector_etfs():
    """update_index_price should include all 11 sector ETFs in indices list."""
    from data.market_us import update_index_price
    import inspect

    # Extract indices list from function source
    source = inspect.getsource(update_index_price)
    expected_etfs = [
        "XLK", "XLY", "XLF", "XLV", "XLP",
        "XLI", "XLE", "XLB", "XLRE", "XLU", "XLC"
    ]

    # Each ETF should appear in source code
    for etf in expected_etfs:
        assert etf in source, f"ETF {etf} not found in update_index_price()"


def test_indices_list_format():
    """Indices list should use (symbol, index_id) tuple format."""
    from data.market_us import update_index_price
    import inspect
    import ast

    source = inspect.getsource(update_index_price)

    # Find indices assignment line
    for line in source.split('\n'):
        if 'indices = [' in line:
            # Verify format: ("XLK", "XLK")
            assert '"XLK", "XLK"' in source or "('XLK', 'XLK')" in source
            break
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_us_index_price.py -v`

Expected: FAIL with "ETF XLK not found in update_index_price()"

---

### Task 2: Extend indices list with sector ETFs

**Files:**
- Modify: `data/market_us.py:94-96`

- [ ] **Step 1: Update indices list**

Replace line 96 in `data/market_us.py`:

```python
indices = [("^GSPC", "SP500"), ("^RUT", "RUSSELL1000")]
```

With:

```python
indices = [
    ("^GSPC", "SP500"),
    ("^RUT", "RUSSELL1000"),
    ("XLK", "XLK"),
    ("XLY", "XLY"),
    ("XLF", "XLF"),
    ("XLV", "XLV"),
    ("XLP", "XLP"),
    ("XLI", "XLI"),
    ("XLE", "XLE"),
    ("XLB", "XLB"),
    ("XLRE", "XLRE"),
    ("XLU", "XLU"),
    ("XLC", "XLC"),
]
```

- [ ] **Step 2: Run test to verify it passes**

Run: `uv run pytest tests/test_us_index_price.py -v`

Expected: PASS

- [ ] **Step 3: Commit changes**

```bash
git add data/market_us.py tests/test_us_index_price.py
git commit -m "$(cat <<'EOF'
feat: add 11 US sector ETFs to daily price collection

XLK/XLY/XLF/XLV/XLP/XLI/XLE/XLB/XLRE/XLU/XLC added to update_index_price().
ETF prices stored in index_prices table, fetched via yfinance.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Verify with production data

**Files:**
- No file changes

- [ ] **Step 1: Run daily update**

Run: `uv run main.py daily --market us`

Expected: Log shows ETF price collection

- [ ] **Step 2: Verify database has ETF data**

Run SQL query:

```sql
SELECT index_id, MIN(date), MAX(date), COUNT(*)
FROM index_prices
WHERE index_id IN ('XLK','XLY','XLF','XLV','XLP','XLI','XLE','XLB','XLRE','XLU','XLC')
GROUP BY index_id;
```

Expected: 11 rows with data from 2010 or ETF inception date

---

## Self-Review Checklist

**1. Spec coverage:**
- ✓ 11 ETFs added to indices list (Task 2)
- ✓ Hardcoded list (Task 2)
- ✓ No indices table registration (Task 2 - no init changes)
- ✓ Stored in index_prices (Task 3 verification)
- ✓ Start date 2010-01-01 (existing logic unchanged)

**2. Placeholder scan:**
- ✓ No TBD/TODO
- ✓ All code blocks complete
- ✓ All commands specified

**3. Type consistency:**
- ✓ indices format: (symbol, index_id) tuple - consistent with existing ^GSPC/^RUT

---

## Notes

**ETF inception dates (yfinance handles automatically):**
- XLRE: 2014-10-07 (data starts from this date, not 2010)
- XLC: 2018-06-18 (data starts from this date, not 2010)

**Existing error handling covers:**
- Empty responses (skip)
- Rate limiting (yfinance retries)
- Missing data (INSERT IGNORE)