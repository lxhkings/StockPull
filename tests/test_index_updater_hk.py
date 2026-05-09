# tests/test_index_updater_hk.py
from unittest.mock import patch
import pandas as pd


def _ak_hsi_df():
    """akshare HK HSI components return shape."""
    return pd.DataFrame({
        "品种代码": ["00700", "09988", "00005"],
        "品种名称": ["腾讯控股", "阿里巴巴-W", "汇丰控股"],
    })


@patch("data.index_updater_hk.ak.index_stock_cons")
def test_fetch_hsi_normalizes_to_hk_canonical(mock_ak):
    from data.index_updater_hk import _fetch_hsi
    mock_ak.return_value = _ak_hsi_df()
    df = _fetch_hsi()
    assert set(df["ticker"]) == {"00700.HK", "09988.HK", "00005.HK"}
    assert "name" in df.columns
