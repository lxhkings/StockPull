from unittest.mock import patch


@patch("jobs.market_hk.stock_updater_hk")
@patch("jobs.market_hk.hsi_csv")
@patch("jobs.market_hk.get_index_tickers")
def test_update_index_delegates_to_hsi(mock_get, mock_idx, mock_stock):
    from jobs.market_hk import update_index

    # prev=["00700.HK"], after hsi update curr=["00700.HK","09988.HK"] → +1 new
    mock_get.side_effect = [
        ["00700.HK"],
        ["00700.HK", "09988.HK"],
    ]
    new_tickers, inserted, removed = update_index()

    mock_idx.update_hsi.assert_called_once()
    assert new_tickers == ["09988.HK"]
    assert inserted == 2
    assert removed == 0


@patch("jobs.market_hk.get_index_tickers", return_value=["00700.HK", "09988.HK"])
def test_list_active_tickers(mock_get):
    from jobs.market_hk import list_active_tickers
    tickers = list_active_tickers()
    assert tickers == ["00700.HK", "09988.HK"]
