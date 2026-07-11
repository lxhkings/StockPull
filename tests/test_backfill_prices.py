from unittest.mock import patch, MagicMock
import pandas as pd

from ts_ingest.backfill_prices import backfill_one, backfill_market


def _bar_df():
    return pd.DataFrame({
        "ts_code": ["600519.SH", "600519.SH"],
        "trade_date": ["20240102", "20240103"],
        "open": [1700.0, 1710.5],
        "high": [1720.0, 1715.0],
        "low":  [1690.0, 1700.0],
        "close": [1715.0, 1705.5],
        "vol":  [12345.0, 23456.0],
    })


def test_backfill_one_writes_with_on_duplicate():
    fake_client = MagicMock()
    fake_client.pro_bar.return_value = _bar_df()
    with patch("ts_ingest.backfill_prices.get_conn") as mock_conn, \
         patch("ts_ingest.backfill_prices.get_client", return_value=fake_client), \
         patch("ts_ingest.backfill_prices.set_sync_ok") as mock_ok:
        cur = MagicMock()
        mock_conn.return_value.__enter__ = lambda s: mock_conn.return_value
        mock_conn.return_value.cursor.return_value.__enter__ = lambda s: cur
        n = backfill_one("600519.SH", market="cn")
    assert n == 2
    sql = cur.executemany.call_args[0][0]
    assert "ON DUPLICATE KEY UPDATE" in sql
    fake_client.pro_bar.assert_called_once()
    kwargs = fake_client.pro_bar.call_args.kwargs
    assert kwargs["adj"] == "qfq"
    mock_ok.assert_called_once()


def test_backfill_one_us_does_not_use_hfq():
    fake_client = MagicMock()
    fake_client.pro_bar.return_value = _bar_df().assign(ts_code="AAPL")
    with patch("ts_ingest.backfill_prices.get_conn") as mock_conn, \
         patch("ts_ingest.backfill_prices.get_client", return_value=fake_client), \
         patch("ts_ingest.backfill_prices.set_sync_ok"):
        cur = MagicMock()
        mock_conn.return_value.cursor.return_value.__enter__ = lambda s: cur
        backfill_one("AAPL", market="us")
    kwargs = fake_client.pro_bar.call_args.kwargs
    assert kwargs.get("asset") == "US"
    assert "adj" not in kwargs or kwargs["adj"] is None


def test_backfill_market_continues_on_per_ticker_failure():
    fake_client = MagicMock()
    fake_client.pro_bar.side_effect = [
        Exception("ticker A failed"),
        _bar_df(),
    ]
    with patch("ts_ingest.backfill_prices.get_conn") as mock_conn, \
         patch("ts_ingest.backfill_prices.get_client", return_value=fake_client), \
         patch("ts_ingest.backfill_prices.set_sync_ok"), \
         patch("ts_ingest.backfill_prices.set_sync_error") as mock_err:
        cur = MagicMock()
        mock_conn.return_value.cursor.return_value.__enter__ = lambda s: cur
        report = backfill_market(["A.SH", "B.SH"], market="cn")
    assert report["ok"] == 1
    assert report["failed"] == ["A.SH"]
    mock_err.assert_called_once()
