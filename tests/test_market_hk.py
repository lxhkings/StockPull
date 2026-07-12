from unittest.mock import patch, MagicMock


@patch("data.market_hk.stock_updater_hk")
@patch("data.market_hk.hsi_csv")
@patch("data.market_hk.get_conn")
def test_update_index_delegates_to_hsi(mock_conn, mock_idx, mock_stock):
    from data.market_hk import update_index

    mock_conn.return_value = MagicMock()

    with patch("data.market_hk.query", return_value=[{"ticker": "00700.HK"}]):
        new_tickers, inserted, removed = update_index()

    mock_idx.update_hsi.assert_called_once()
    assert isinstance(inserted, int)
    assert isinstance(removed, int)


@patch("data.market_hk.get_index_tickers", return_value=["00700.HK", "09988.HK"])
def test_list_active_tickers(mock_get):
    from data.market_hk import list_active_tickers
    tickers = list_active_tickers()
    assert tickers == ["00700.HK", "09988.HK"]
