"""Tests for CN market module."""
from unittest.mock import patch


@patch("jobs.market_cn.backfill_stocks_a")
@patch("jobs.market_cn.query")
def test_update_index_delegates_to_backfill_stocks_a(mock_query, mock_backfill):
    """update_index should call backfill_stocks_a and return stats."""
    from jobs.market_cn import update_index

    mock_query.side_effect = [
        [{"n": 100}],  # prev
        [{"n": 105}],  # curr
    ]
    mock_backfill.return_value = 5

    new_tickers, inserted, removed = update_index()

    mock_backfill.assert_called_once()
    assert inserted == 5
    assert removed == 0
    assert new_tickers == []
    assert mock_query.call_count == 2


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


def test_intraday_is_noop():
    from jobs.market_cn import intraday
    assert intraday() == {}
    assert intraday(["1h"], full_rebase=True) == {}
