from unittest.mock import patch, MagicMock
import pandas as pd
from datetime import date


def _ak_hk_hist_df():
    """Simulate akshare stock_hk_hist return."""
    return pd.DataFrame({
        "日期": ["2024-01-02", "2024-01-03"],
        "开盘": [350.0, 355.0],
        "收盘": [352.0, 360.0],
        "最高": [358.0, 362.0],
        "最低": [348.0, 353.0],
        "成交量": [5000000, 6000000],
        "成交额": [1750000000, 2160000000],
        "振幅": [2.8, 2.5],
        "涨跌幅": [0.57, 2.27],
        "涨跌额": [2.0, 8.0],
        "换手率": [0.2, 0.24],
    })


@patch("data.stock_updater_hk.ak.stock_hk_hist")
def test_fetch_prices_hk_normalizes_columns(mock_ak):
    from data.stock_updater_hk import _fetch_prices_hk
    mock_ak.return_value = _ak_hk_hist_df()
    df = _fetch_prices_hk("00700.HK", "20240101", "20240105")
    assert set(df.columns) == {"date", "open", "high", "low", "close", "volume"}
    assert len(df) == 2
    assert df["close"].iloc[0] == 352.0


@patch("data.stock_updater_hk._fetch_prices_hk")
@patch("data.stock_updater_hk.get_conn")
def test_update_prices_batch_skips_already_synced(mock_conn, mock_fetch):
    """Tickers whose last sync is today should be skipped."""
    from data.stock_updater_hk import update_prices_batch

    cur = MagicMock()
    cur.fetchone.return_value = (date.today(),)
    mock_conn.return_value.cursor.return_value.__enter__.return_value = cur
    mock_fetch.return_value = pd.DataFrame()

    result = update_prices_batch(["00700.HK"])
    assert result["00700.HK"] == "skipped"
    mock_fetch.assert_not_called()
