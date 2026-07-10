from unittest.mock import MagicMock, patch

import pandas as pd

from ts_ingest.backfill_shareholder_return import backfill_dividend_one, backfill_dividend


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
