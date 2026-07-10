from datetime import date
from unittest.mock import MagicMock, patch

import pandas as pd

from ts_ingest.backfill_shareholder_return import (
    _date_windows, _last_synced_ann_date,
    backfill_repurchase_window, backfill_repurchase,
    backfill_dividend_one, backfill_dividend,
)


def test_backfill_dividend_one_writes_flat_columns():
    fake_client = MagicMock()
    fake_client.call.return_value = pd.DataFrame({
        "ts_code": ["600519.SH"], "end_date": ["20231231"], "ann_date": ["20240328"],
        "div_proc": ["实施"], "stk_div": [0.0], "stk_bo_rate": [0.0], "stk_co_rate": [0.0],
        "cash_div": [19.29], "cash_div_tax": [21.43], "record_date": ["20240612"],
        "ex_date": ["20240613"], "pay_date": ["20240613"], "div_listdate": [None],
        "imp_ann_date": ["20240608"], "base_date": ["20231231"], "base_share": [1256197.8],
    })
    with patch("ts_ingest.backfill_shareholder_return.get_conn") as mock_conn, \
         patch("ts_ingest.backfill_shareholder_return.get_client", return_value=fake_client):
        cur = MagicMock()
        mock_conn.return_value.__enter__ = lambda s: mock_conn.return_value
        mock_conn.return_value.cursor.return_value.__enter__ = lambda s: cur
        n = backfill_dividend_one("600519.SH")
    assert n == 1
    sql = cur.executemany.call_args[0][0]
    assert "INSERT INTO cn_dividend" in sql
    assert "ON DUPLICATE KEY UPDATE" in sql
    row = cur.executemany.call_args[0][1][0]
    assert row[0] == "600519.SH"
    assert row[1] == "2023-12-31"


def test_backfill_dividend_one_returns_zero_on_empty_response():
    fake_client = MagicMock()
    fake_client.call.return_value = pd.DataFrame()
    with patch("ts_ingest.backfill_shareholder_return.get_client", return_value=fake_client):
        n = backfill_dividend_one("600519.SH")
    assert n == 0


def test_backfill_dividend_loops_all_tickers():
    with patch("ts_ingest.backfill_shareholder_return._list_a_share_tickers",
               return_value=["600519.SH", "000001.SZ"]), \
         patch("ts_ingest.backfill_shareholder_return.backfill_dividend_one",
               return_value=2) as one:
        result = backfill_dividend()
    assert one.call_count == 2
    assert result == {"rows": 4, "tickers": 2}


def test_date_windows_splits_by_window_days():
    windows = _date_windows("20240101", "20240301", window_days=31)
    assert windows[0] == ("20240101", "20240131")
    assert windows[-1][1] == "20240301"


def test_date_windows_single_day_range():
    windows = _date_windows("20240101", "20240101", window_days=90)
    assert windows == [("20240101", "20240101")]


def test_last_synced_ann_date_returns_none_on_empty_table():
    with patch("ts_ingest.backfill_shareholder_return.get_conn") as mock_conn:
        cur = MagicMock()
        cur.fetchone.return_value = (None,)
        mock_conn.return_value.__enter__ = lambda s: mock_conn.return_value
        mock_conn.return_value.cursor.return_value.__enter__ = lambda s: cur
        assert _last_synced_ann_date("cn_repurchase") is None


def test_last_synced_ann_date_formats_existing_max():
    with patch("ts_ingest.backfill_shareholder_return.get_conn") as mock_conn:
        cur = MagicMock()
        cur.fetchone.return_value = (date(2024, 3, 28),)
        mock_conn.return_value.__enter__ = lambda s: mock_conn.return_value
        mock_conn.return_value.cursor.return_value.__enter__ = lambda s: cur
        assert _last_synced_ann_date("cn_repurchase") == "20240328"


def test_backfill_repurchase_window_writes_flat_columns():
    fake_client = MagicMock()
    fake_client.call.return_value = pd.DataFrame({
        "ts_code": ["600519.SH"], "ann_date": ["20240115"], "end_date": ["20241231"],
        "proc": ["实施中"], "exp_date": ["20241231"], "vol": [1000000.0],
        "amount": [150000000.0], "high_limit": [1800.0], "low_limit": [1200.0],
    })
    with patch("ts_ingest.backfill_shareholder_return.get_conn") as mock_conn, \
         patch("ts_ingest.backfill_shareholder_return.get_client", return_value=fake_client):
        cur = MagicMock()
        mock_conn.return_value.__enter__ = lambda s: mock_conn.return_value
        mock_conn.return_value.cursor.return_value.__enter__ = lambda s: cur
        n = backfill_repurchase_window("20240101", "20241231")
    assert n == 1
    sql = cur.executemany.call_args[0][0]
    assert "INSERT INTO cn_repurchase" in sql
    assert "ON DUPLICATE KEY UPDATE" in sql


def test_backfill_repurchase_defaults_to_incremental_from_last_synced_date():
    with patch("ts_ingest.backfill_shareholder_return._last_synced_ann_date",
               return_value="20240328"), \
         patch("ts_ingest.backfill_shareholder_return._date_windows") as mock_windows, \
         patch("ts_ingest.backfill_shareholder_return.backfill_repurchase_window", return_value=0):
        mock_windows.return_value = []
        backfill_repurchase()
    assert mock_windows.call_args[0][0] == "20240329"


def test_backfill_repurchase_falls_back_to_full_history_when_table_empty():
    with patch("ts_ingest.backfill_shareholder_return._last_synced_ann_date", return_value=None), \
         patch("ts_ingest.backfill_shareholder_return._date_windows") as mock_windows, \
         patch("ts_ingest.backfill_shareholder_return.backfill_repurchase_window", return_value=0):
        mock_windows.return_value = []
        backfill_repurchase()
    assert mock_windows.call_args[0][0] == "20100101"


def test_backfill_repurchase_explicit_start_overrides_incremental_default():
    with patch("ts_ingest.backfill_shareholder_return._last_synced_ann_date",
               return_value="20240328"), \
         patch("ts_ingest.backfill_shareholder_return._date_windows") as mock_windows, \
         patch("ts_ingest.backfill_shareholder_return.backfill_repurchase_window", return_value=0):
        mock_windows.return_value = []
        backfill_repurchase(start="20200101")
    assert mock_windows.call_args[0][0] == "20200101"
