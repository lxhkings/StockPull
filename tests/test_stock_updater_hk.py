# tests/test_stock_updater_hk.py
from unittest.mock import patch, MagicMock
import pandas as pd
from datetime import date


def _ak_hk_hist_df():
    """akshare stock_hk_daily output shape."""
    return pd.DataFrame({
        "date":   ["2024-01-02", "2024-01-03"],
        "open":   [310.0, 312.0],
        "high":   [315.0, 316.0],
        "low":    [308.0, 310.0],
        "close":  [314.0, 315.0],
        "volume": [10_000_000, 11_000_000],
    })


@patch("data.stock_updater_hk.ak.stock_hk_daily")
def test_fetch_normalizes_columns_and_filters_range(mock_ak):
    from data.stock_updater_hk import _fetch_one_akshare
    mock_ak.return_value = _ak_hk_hist_df()
    df = _fetch_one_akshare("00700.HK", date(2024, 1, 1), date(2024, 1, 5))
    assert list(df.columns) == ["ticker", "date", "open", "high", "low", "close", "volume"]
    assert df["ticker"].iloc[0] == "00700.HK"
    assert all(df["date"] >= date(2024, 1, 1))
    assert all(df["date"] <= date(2024, 1, 5))
