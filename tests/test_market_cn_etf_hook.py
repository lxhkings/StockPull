"""Verify update_index_price() invokes ETF updater after CSI800."""
from unittest.mock import patch, MagicMock
import pandas as pd
from datetime import date


@patch("data.etf_updater_cn.update_etf_prices")
@patch("data.market_cn.query")
@patch("data.market_cn.execute")
@patch("data.market_cn.get_client")
def test_update_index_price_calls_etf_updater(mock_get_client, mock_execute, mock_query, mock_etf_update):
    """CSI800 count + ETF count are summed."""
    mock_query.return_value = [{"d": date(2026, 5, 10)}]

    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    mock_client.call.return_value = pd.DataFrame({
        "ts_code": ["000906.SH"],
        "trade_date": ["20260513"],
        "close": [5675.0],
    })
    mock_execute.return_value = 1   # CSI800 row

    mock_etf_update.return_value = 42  # ETF rows

    from data.market_cn import update_index_price
    total = update_index_price()

    assert total == 1 + 42
    mock_etf_update.assert_called_once_with()