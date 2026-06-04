from unittest.mock import MagicMock, patch

from futu_ingest.sync import fresh_tickers, mark_ok, mark_error


def test_fresh_tickers_returns_set_from_query():
    with patch("futu_ingest.sync.get_conn") as mock_conn:
        cur = MagicMock()
        cur.fetchall.return_value = [("AAPL",), ("MSFT",)]
        mock_conn.return_value.cursor.return_value.__enter__ = lambda s: cur
        result = fresh_tickers("us_financial", 80)
    assert result == {"AAPL", "MSFT"}
    sql, params = cur.execute.call_args[0]
    assert "status='ok'" in sql
    assert "last_run" in sql
    assert params == ("us_financial", 80)


def test_fresh_tickers_empty():
    with patch("futu_ingest.sync.get_conn") as mock_conn:
        cur = MagicMock()
        cur.fetchall.return_value = []
        mock_conn.return_value.cursor.return_value.__enter__ = lambda s: cur
        assert fresh_tickers("us_financial", 80) == set()


def test_mark_ok_calls_set_sync_ok_with_today():
    with patch("futu_ingest.sync.get_conn") as mock_conn, \
         patch("futu_ingest.sync.set_sync_ok") as sso:
        conn = mock_conn.return_value
        mark_ok("AAPL", "us_financial", 12)
    args = sso.call_args[0]
    assert args[0] is conn and args[1] == "AAPL" and args[2] == "us_financial"
    assert args[4] == 12
    conn.close.assert_called_once()


def test_mark_error_calls_set_sync_error():
    with patch("futu_ingest.sync.get_conn") as mock_conn, \
         patch("futu_ingest.sync.set_sync_error") as sse:
        conn = mock_conn.return_value
        mark_error("AAPL", "us_financial", "boom")
    args = sse.call_args[0]
    assert args[1] == "AAPL" and args[2] == "us_financial" and args[3] == "boom"
    conn.close.assert_called_once()