from unittest.mock import patch, MagicMock
import pandas as pd


@patch("data.market_cn.stock_updater_cn")
@patch("data.market_cn.index_updater_cn")
@patch("data.market_cn.get_conn")
def test_update_index_delegates_to_csi800(mock_conn, mock_idx, mock_stock):
    from data.market_cn import update_index

    # get_conn returns a mock connection
    mock_conn.return_value = MagicMock()

    # index updater returns (new_tickers, inserted, removed) indirectly
    # We mock the internal _latest_snapshot_tickers by mocking query
    with patch("data.market_cn.query", return_value=[{"ticker": "600519.SH"}]):
        new_tickers, inserted, removed = update_index()

    mock_idx.update_csi800.assert_called_once()
    assert isinstance(inserted, int)
    assert isinstance(removed, int)


@patch("data.market_cn.get_index_tickers", return_value=["600519.SH", "000001.SZ"])
def test_list_active_tickers(mock_get):
    from data.market_cn import list_active_tickers
    tickers = list_active_tickers()
    assert tickers == ["600519.SH", "000001.SZ"]
