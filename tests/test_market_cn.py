"""Tests for CN market module."""
from unittest.mock import patch, MagicMock


@patch("jobs.market_cn.backfill_stocks_a")
@patch("jobs.market_cn.get_conn")
def test_update_index_delegates_to_backfill_stocks_a(mock_conn, mock_backfill):
    """update_index should call backfill_stocks_a and return stats."""
    from jobs.market_cn import update_index

    # Mock connection for count queries - fetchone returns tuples
    mock_cursor = MagicMock()
    mock_cursor.fetchone.side_effect = [(100,), (105,)]  # prev_count=100, curr_count=105
    mock_connection = MagicMock()
    mock_connection.cursor.return_value = mock_cursor
    mock_connection.close = MagicMock()
    mock_conn.return_value = mock_connection

    # backfill_stocks_a returns inserted count
    mock_backfill.return_value = 5

    new_tickers, inserted, removed = update_index()

    mock_backfill.assert_called_once()
    assert inserted == 5
    assert removed == 0  # No constituent tracking anymore
    assert new_tickers == []  # Returns empty since list_active_tickers reads from DB


@patch("jobs.market_cn.query")
def test_list_active_tickers(mock_query):
    """list_active_tickers should return tickers from stocks table."""
    from jobs.market_cn import list_active_tickers

    mock_query.return_value = [
        {"ticker": "600519.SH"},
        {"ticker": "000001.SZ"},
        {"ticker": "300750.SZ"},
    ]

    tickers = list_active_tickers()

    assert tickers == ["600519.SH", "000001.SZ", "300750.SZ"]
    mock_query.assert_called_once()