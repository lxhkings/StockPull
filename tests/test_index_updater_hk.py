from unittest.mock import patch, MagicMock
import pandas as pd
from datetime import date


def _hsi_constituents_df():
    return pd.DataFrame({
        "品种代码": ["00700", "09988", "00005"],
        "品种名称": ["腾讯控股", "阿里巴巴-SW", "汇丰控股"],
    })


@patch("data.index_updater_hk.ak.index_stock_cons")
def test_fetch_hsi_normalizes_to_canonical_tickers(mock_ak):
    from data.index_updater_hk import _fetch_hsi
    mock_ak.return_value = _hsi_constituents_df()
    df = _fetch_hsi()
    assert set(df["ticker"]) == {"00700.HK", "09988.HK", "00005.HK"}
    assert "name" in df.columns


@patch("data.index_updater_hk._fetch_hsi")
@patch("data.index_updater_hk.get_conn")
def test_update_hsi_skips_when_today_already_done(mock_conn, mock_fetch):
    """If snapshot already exists for today, skip without calling akshare."""
    from data.index_updater_hk import update_hsi
    cur = MagicMock()
    cur.fetchone.return_value = (date.today(),)
    mock_conn.return_value.cursor.return_value.__enter__.return_value = cur
    update_hsi()
    mock_fetch.assert_not_called()
