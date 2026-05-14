"""Tests for CN market index price fetching via tushare."""
import pytest
from unittest.mock import patch, MagicMock
import pandas as pd
from datetime import date


@patch("data.market_cn.query")
@patch("data.market_cn.execute")
@patch("data.market_cn.get_client")
def test_update_index_price_uses_tushare_index_daily(mock_get_client, mock_execute, mock_query):
    """update_index_price should call tushare index_daily API, not akshare."""
    # Setup: last date in DB is 2026-05-10
    mock_query.return_value = [{"d": date(2026, 5, 10)}]

    # Mock tushare client
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client

    # Mock tushare index_daily response
    raw_df = pd.DataFrame({
        "ts_code": ["000906.SH", "000906.SH"],
        "trade_date": ["20260513", "20260511"],
        "close": [5675.0, 5610.0],
        "open": [5576.0, 5636.0],
        "high": [5678.0, 5636.0],
        "low": [5576.0, 5583.0],
    })
    mock_client.call.return_value = raw_df

    # Execute
    from data.market_cn import update_index_price
    count = update_index_price()

    # Verify tushare client was called with correct parameters
    assert mock_client.call.called
    call_args = mock_client.call.call_args
    assert call_args[0][0] == "index_daily"
    assert call_args[1]["ts_code"] == "000906.SH"
    # start_date should be the last date in DB
    assert call_args[1]["start_date"] == "20260510"

    # Verify execute was called with filtered data (date > last_date)
    assert mock_execute.called
    # Both 20260513 and 20260511 are > 2026-05-10, so both should be inserted
    insert_call = mock_execute.call_args
    rows = insert_call[0][1]  # second argument is the rows list
    assert len(rows) == 2
    # Check the dates are correct (sorted by date descending from tushare)
    assert rows[0][0] == date(2026, 5, 13)  # date
    assert rows[0][1] == "CSI800"  # index_id
    assert rows[0][2] == 5675.0  # close
    assert rows[1][0] == date(2026, 5, 11)  # date
    assert rows[1][1] == "CSI800"  # index_id
    assert rows[1][2] == 5610.0  # close


@patch("data.market_cn.query")
@patch("data.market_cn.execute")
@patch("data.market_cn.get_client")
def test_update_index_price_empty_response(mock_get_client, mock_execute, mock_query):
    """Should return 0 when tushare returns empty data."""
    mock_query.return_value = [{"d": date(2026, 5, 10)}]

    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    mock_client.call.return_value = pd.DataFrame()  # Empty response

    from data.market_cn import update_index_price
    count = update_index_price()

    assert count == 0
    assert not mock_execute.called


@patch("data.market_cn.query")
@patch("data.market_cn.execute")
@patch("data.market_cn.get_client")
def test_update_index_price_no_last_date(mock_get_client, mock_execute, mock_query):
    """Should fetch all data when no last_date exists."""
    mock_query.return_value = [{"d": None}]  # No last date

    mock_client = MagicMock()
    mock_get_client.return_value = mock_client

    raw_df = pd.DataFrame({
        "ts_code": ["000906.SH"],
        "trade_date": ["20260513"],
        "close": [5675.0],
    })
    mock_client.call.return_value = raw_df

    from data.market_cn import update_index_price
    count = update_index_price()

    # When no last_date, start_date should be None
    call_args = mock_client.call.call_args
    assert call_args[1]["start_date"] is None

    # All data should be inserted
    insert_call = mock_execute.call_args
    rows = insert_call[0][1]
    assert len(rows) == 1


@patch("data.market_cn.query")
@patch("data.market_cn.execute")
@patch("data.market_cn.get_client")
def test_update_index_price_handles_exception(mock_get_client, mock_execute, mock_query):
    """Should return 0 and log error on tushare API failure."""
    mock_query.return_value = [{"d": date(2026, 5, 10)}]

    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    mock_client.call.side_effect = Exception("API error")

    from data.market_cn import update_index_price
    count = update_index_price()

    assert count == 0
    assert not mock_execute.called