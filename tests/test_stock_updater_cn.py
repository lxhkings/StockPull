from unittest.mock import patch, MagicMock
import pandas as pd
from datetime import date


def _ak_hist_df():
    """Simulate akshare stock_zh_a_hist return (后复权)."""
    return pd.DataFrame({
        "日期": ["2024-01-02", "2024-01-03"],
        "开盘": [1800.0, 1810.0],
        "收盘": [1805.0, 1820.0],
        "最高": [1815.0, 1825.0],
        "最低": [1795.0, 1800.0],
        "成交量": [10000, 12000],
    })


@patch("data.stock_updater_cn.ak.stock_zh_a_hist")
def test_fetch_prices_cn_normalizes_columns(mock_ak):
    from data.stock_updater_cn import _fetch_prices_cn
    mock_ak.return_value = _ak_hist_df()
    df = _fetch_prices_cn("600519.SH", "2024-01-01", "2024-01-05")
    assert set(df.columns) == {"date", "open", "high", "low", "close", "volume"}
    assert len(df) == 2
    assert df["close"].iloc[0] == 1805.0


@patch("data.stock_updater_cn._fetch_prices_cn")
@patch("data.stock_updater_cn.get_conn")
def test_update_prices_batch_skips_already_synced(mock_conn, mock_fetch):
    """Tickers whose last sync is today should be skipped."""
    from data.stock_updater_cn import update_prices_batch

    cur = MagicMock()
    # get_last_sync returns today → skip
    cur.fetchone.return_value = (date.today(),)
    mock_conn.return_value.cursor.return_value.__enter__.return_value = cur
    mock_fetch.return_value = pd.DataFrame()

    result = update_prices_batch(["600519.SH"])
    assert result["600519.SH"] == "skipped"
    mock_fetch.assert_not_called()
