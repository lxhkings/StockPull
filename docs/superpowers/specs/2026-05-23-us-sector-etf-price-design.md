# US Sector ETF Price Collection Design

## Overview

Add 11 US sector ETF daily price collection to the existing `daily --market us` pipeline.

## ETF List

| Ticker | Sector | Name |
|--------|--------|------|
| XLK | Technology | Technology Select Sector SPDR Fund |
| XLY | Consumer Discretionary | Consumer Discretionary Select Sector SPDR Fund |
| XLF | Financials | Financial Select Sector SPDR Fund |
| XLV | Health Care | Health Care Select Sector SPDR Fund |
| XLP | Consumer Staples | Consumer Staples Select Sector SPDR Fund |
| XLI | Industrials | Industrial Select Sector SPDR Fund |
| XLE | Energy | Energy Select Sector SPDR Fund |
| XLB | Materials | Materials Select Sector SPDR Fund |
| XLRE | Real Estate | Real Estate Select Sector SPDR Fund |
| XLU | Utilities | Utilities Select Sector SPDR Fund |
| XLC | Communication Services | Communication Services Select Sector SPDR Fund |

## Data Source

- yfinance (Yahoo Finance API)
- Start date: 2010-01-01
- ETFs launched after 2010 will automatically return data from their inception date

## Storage

- Table: `index_prices`
- Fields: `date`, `index_id`, `close`
- `index_id` uses ETF ticker directly (e.g., "XLK", not a fictional index ID)

## Design Decisions

### No indices Table Registration

ETFs will NOT be registered in the `indices` table. This matches the existing approach for ^GSPC/^RUT symbols which are also not registered. The `init` command remains unchanged.

### Hardcoded ETF List

ETFs will be hardcoded in `update_index_price()` function, matching the existing pattern for index symbols. No configuration file needed for 11 static tickers.

## Implementation

### Single File Change

**File:** `data/market_us.py`

**Function:** `update_index_price()`

**Change:** Extend the `indices` list from:
```python
indices = [("^GSPC", "SP500"), ("^RUT", "RUSSELL1000")]
```

To:
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

### No Other Changes

- Pipeline flow unchanged
- CLI arguments unchanged
- Database schema unchanged
- No new tables or columns

## Data Flow

```
uv run main.py daily --market us
  → Pipeline(mod).daily()
    → mod.update_index_price()
      → yfinance.download for each symbol
        → INSERT IGNORE index_prices (date, index_id, close)
```

## Verification

```bash
# Run daily update
uv run main.py daily --market us

# Verify ETF data
SELECT index_id, MIN(date), MAX(date), COUNT(*)
FROM index_prices
WHERE index_id IN ('XLK','XLY','XLF','XLV','XLP','XLI','XLE','XLB','XLRE','XLU','XLC')
GROUP BY index_id;
```

## Edge Cases

1. **ETF launched after 2010**: yfinance automatically returns data from inception date (e.g., XLRE launched 2014-10-07, XLC launched 2018-06-18)
2. **Missing data**: Existing error handling in `update_index_price()` handles empty responses
3. **Rate limiting**: Existing yfinance call pattern already handles Yahoo API limits

## Success Criteria

- `uv run main.py daily --market us` successfully collects 11 ETF prices
- All 11 ETFs have data in `index_prices` table
- Existing SP500/Russell1000 collection continues working