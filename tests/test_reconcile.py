import pandas as pd
from data.reconcile import reconcile_prices


def test_matching_prices_return_empty():
    primary = pd.DataFrame({
        "ticker": ["600519.SH", "600519.SH"],
        "date": ["2024-01-02", "2024-01-03"],
        "close": [1800.0, 1810.0],
    })
    secondary = primary.copy()
    mismatches = reconcile_prices(primary, secondary, tolerance=0.005)
    assert mismatches.empty


def test_divergent_prices_return_mismatched_rows():
    primary = pd.DataFrame({
        "ticker": ["600519.SH"],
        "date": ["2024-01-02"],
        "close": [1800.0],
    })
    secondary = pd.DataFrame({
        "ticker": ["600519.SH"],
        "date": ["2024-01-02"],
        "close": [1850.0],  # 2.8% off — exceeds 0.5%
    })
    mismatches = reconcile_prices(primary, secondary, tolerance=0.005)
    assert len(mismatches) == 1
    assert "diff_pct" in mismatches.columns
