# tests/test_index_updater_hk.py
from apis.static.hsi_csv import _fetch_hsi


def test_fetch_hsi_from_csv():
    """Test HSI fetch from actual CSV file."""
    df = _fetch_hsi()

    # Should find HSI constituents
    assert df is not None
    assert len(df) > 70  # HSI has 83 constituents
    assert "ticker" in df.columns
    assert "name" in df.columns

    # Check format: 5-digit code + .HK suffix
    assert all(df["ticker"].str.endswith(".HK"))
    assert all(df["ticker"].str.len() == 8)  # 5 digits + ".HK"

    # Check known constituent
    assert "00700.HK" in set(df["ticker"])  # Tencent