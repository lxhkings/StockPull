from unittest.mock import patch, MagicMock
import pandas as pd
from datetime import date


def _ak_csi800_df():
    return pd.DataFrame({
        "成分券代码": ["600519", "000001", "300750"],
        "成分券名称": ["贵州茅台", "平安银行", "宁德时代"],
        "行业": ["食品饮料", "银行", "电力设备"],
    })


@patch("data.index_updater_cn.ak.index_stock_cons_csindex")
def test_fetch_csi800_normalizes_to_canonical_tickers(mock_ak):
    from data.index_updater_cn import _fetch_csi800
    mock_ak.return_value = _ak_csi800_df()
    df = _fetch_csi800()
    assert set(df["ticker"]) == {"600519.SH", "000001.SZ", "300750.SZ"}
    assert "name" in df.columns
    assert "sector" in df.columns


@patch("data.index_updater_cn._fetch_csi800")
@patch("data.index_updater_cn.get_conn")
def test_update_csi800_skips_when_today_already_done(mock_conn, mock_fetch):
    """If snapshot already exists for today, skip without calling akshare."""
    from data.index_updater_cn import update_csi800
    cur = MagicMock()
    cur.fetchone.return_value = (date.today(),)
    mock_conn.return_value.cursor.return_value.__enter__.return_value = cur
    update_csi800()
    mock_fetch.assert_not_called()
