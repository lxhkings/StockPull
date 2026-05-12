from unittest.mock import patch, MagicMock
import json
import pandas as pd

from ts_ingest.backfill_financial import (
    quarterly_periods, backfill_period, backfill_all,
)


def test_quarterly_periods_15_years_returns_60():
    periods = quarterly_periods("20100101", "20241231")
    assert len(periods) == 60
    assert periods[0] == "20100331"
    assert periods[-1] == "20241231"


def test_backfill_period_writes_with_raw_payload_json():
    fake_client = MagicMock()
    fake_client.call.return_value = pd.DataFrame({
        "ts_code":     ["600519.SH"],
        "ann_date":    ["20240328"],
        "f_ann_date":  ["20240328"],
        "end_date":    ["20231231"],
        "report_type": ["1"],
        "comp_type":   ["1"],
        "total_revenue": [150000000000.0],
        "n_income":      [74700000000.0],
    })
    with patch("ts_ingest.backfill_financial.get_conn") as mock_conn, \
         patch("ts_ingest.backfill_financial.get_client", return_value=fake_client):
        cur = MagicMock()
        mock_conn.return_value.__enter__ = lambda s: mock_conn.return_value
        mock_conn.return_value.cursor.return_value.__enter__ = lambda s: cur
        n = backfill_period("income_vip", "fin_income", "20231231")
    assert n == 1
    args = cur.executemany.call_args
    sql = args[0][0]
    assert "INSERT INTO fin_income" in sql
    assert "ON DUPLICATE KEY UPDATE" in sql
    row = args[0][1][0]
    payload = json.loads(row[6])  # raw_payload at index 6
    assert payload["total_revenue"] == 150000000000.0


def test_backfill_all_calls_4_apis_per_period():
    fake_client = MagicMock()
    fake_client.call.return_value = pd.DataFrame({
        "ts_code": ["x"], "ann_date": ["20240328"], "f_ann_date": ["20240328"],
        "end_date": ["20231231"], "report_type": ["1"], "comp_type": ["1"],
    })
    with patch("ts_ingest.backfill_financial.get_conn") as mock_conn, \
         patch("ts_ingest.backfill_financial.get_client", return_value=fake_client):
        cur = MagicMock()
        mock_conn.return_value.cursor.return_value.__enter__ = lambda s: cur
        backfill_all(periods=["20231231"])
    # income, balancesheet, cashflow, fina_indicator
    assert fake_client.call.call_count == 4
