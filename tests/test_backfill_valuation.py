from datetime import date
from unittest.mock import MagicMock, patch

import pandas as pd

from ts_ingest.backfill_valuation import backfill_all, backfill_day, _last_synced_date


def test_backfill_day_writes_flat_columns():
    fake_client = MagicMock()
    fake_client.call.return_value = pd.DataFrame({
        "ts_code": ["600519.SH"], "trade_date": ["20260706"],
        "close": [1524.0], "turnover_rate": [0.31], "volume_ratio": [1.9],
        "pe": [25.6], "pe_ttm": [23.15], "pb": [9.22], "ps": [12.96],
        "ps_ttm": [11.59], "total_mv": [191444544.72], "circ_mv": [191444544.72],
    })
    with patch("ts_ingest.backfill_valuation.get_conn") as mock_conn, \
         patch("ts_ingest.backfill_valuation.get_client", return_value=fake_client):
        cur = MagicMock()
        mock_conn.return_value.__enter__ = lambda s: mock_conn.return_value
        mock_conn.return_value.cursor.return_value.__enter__ = lambda s: cur
        n = backfill_day("20260706")
    assert n == 1
    args = cur.executemany.call_args
    sql = args[0][0]
    assert "INSERT INTO cn_valuation_snapshot" in sql
    assert "ON DUPLICATE KEY UPDATE" in sql
    row = args[0][1][0]
    assert row[0] == "600519.SH"
    assert row[1] == "2026-07-06"


def test_last_synced_date_returns_none_on_empty_table():
    with patch("ts_ingest.backfill_valuation.get_conn") as mock_conn:
        cur = MagicMock()
        cur.fetchone.return_value = (None,)
        mock_conn.return_value.__enter__ = lambda s: mock_conn.return_value
        mock_conn.return_value.cursor.return_value.__enter__ = lambda s: cur
        assert _last_synced_date() is None


def test_last_synced_date_formats_existing_max():
    with patch("ts_ingest.backfill_valuation.get_conn") as mock_conn:
        cur = MagicMock()
        cur.fetchone.return_value = (date(2026, 7, 6),)
        mock_conn.return_value.__enter__ = lambda s: mock_conn.return_value
        mock_conn.return_value.cursor.return_value.__enter__ = lambda s: cur
        assert _last_synced_date() == "20260706"


def test_backfill_all_defaults_to_incremental_from_last_synced_date():
    with patch("ts_ingest.backfill_valuation._last_synced_date", return_value="20260706"), \
         patch("ts_ingest.backfill_valuation._trading_dates") as mock_dates, \
         patch("ts_ingest.backfill_valuation.backfill_day", return_value=0):
        mock_dates.return_value = []
        backfill_all()
    # start = day after last synced date, not TUSHARE_BACKFILL_START
    mock_dates.assert_called_once_with("20260707")


def test_backfill_all_falls_back_to_full_history_when_table_empty():
    with patch("ts_ingest.backfill_valuation._last_synced_date", return_value=None), \
         patch("ts_ingest.backfill_valuation._trading_dates") as mock_dates, \
         patch("ts_ingest.backfill_valuation.backfill_day", return_value=0):
        mock_dates.return_value = []
        backfill_all()
    mock_dates.assert_called_once_with("20100101")


def test_backfill_all_explicit_start_overrides_incremental_default():
    with patch("ts_ingest.backfill_valuation._last_synced_date", return_value="20260706"), \
         patch("ts_ingest.backfill_valuation._trading_dates") as mock_dates, \
         patch("ts_ingest.backfill_valuation.backfill_day", return_value=0):
        mock_dates.return_value = []
        backfill_all(start="20200101")
    mock_dates.assert_called_once_with("20200101")
