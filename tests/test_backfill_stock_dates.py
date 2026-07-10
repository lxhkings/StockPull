from unittest.mock import MagicMock, patch

import pandas as pd

from ts_ingest.backfill_stock_dates import backfill_stock_dates, _sync_status


def test_sync_status_updates_matched_rows():
    fake_client = MagicMock()
    fake_client.call.return_value = pd.DataFrame({
        "ts_code": ["600519.SH", "000001.SZ"],
        "list_date": ["19940103", "19910403"],
        "delist_date": [None, None],
    })
    with patch("ts_ingest.backfill_stock_dates.get_conn") as mock_conn, \
         patch("ts_ingest.backfill_stock_dates.get_client", return_value=fake_client):
        cur = MagicMock()
        cur.rowcount = 1
        mock_conn.return_value.__enter__ = lambda s: mock_conn.return_value
        mock_conn.return_value.cursor.return_value.__enter__ = lambda s: cur
        result = _sync_status("L")

    assert result == {"status": "L", "rows": 2, "matched": 2}
    assert cur.execute.call_count == 2
    args = cur.execute.call_args_list[0]
    assert "UPDATE stocks SET list_date=%s, delist_date=%s WHERE ticker=%s" in args[0][0]
    assert args[0][1] == ("1994-01-03", None, "600519.SH")


def test_backfill_stock_dates_calls_both_statuses():
    fake_client = MagicMock()
    fake_client.call.return_value = pd.DataFrame({
        "ts_code": ["600519.SH"], "list_date": ["19940103"], "delist_date": [None],
    })
    with patch("ts_ingest.backfill_stock_dates.get_conn") as mock_conn, \
         patch("ts_ingest.backfill_stock_dates.get_client", return_value=fake_client):
        cur = MagicMock()
        cur.rowcount = 1
        mock_conn.return_value.__enter__ = lambda s: mock_conn.return_value
        mock_conn.return_value.cursor.return_value.__enter__ = lambda s: cur
        result = backfill_stock_dates()

    assert set(result.keys()) == {"listed", "delisted"}
    assert result["listed"]["status"] == "L"
    assert result["delisted"]["status"] == "D"
    assert fake_client.call.call_count == 2
