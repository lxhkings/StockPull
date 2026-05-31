import json
from unittest.mock import MagicMock, patch

from futu_ingest.backfill_actions import backfill_dividends, backfill_splits


def test_backfill_dividends_upserts_key_dates():
    client = MagicMock()
    client.call.return_value = {"dividend_list": [{
        "ex_date": "2026-02-07",
        "pub_date": "2026-01-30",
        "record_date": "2026-02-10",
        "dividend_payable_date": "2026-02-13",
        "per_cash_div": 0.26,
    }]}
    with patch("futu_ingest.backfill_actions.get_conn") as mock_conn:
        cur = MagicMock()
        mock_conn.return_value.__enter__ = lambda s: mock_conn.return_value
        mock_conn.return_value.cursor.return_value.__enter__ = lambda s: cur
        n = backfill_dividends(client, "AAPL")
    assert n == 1
    sql = cur.executemany.call_args[0][0]
    assert "INSERT INTO us_dividends" in sql
    row = cur.executemany.call_args[0][1][0]
    # row = (ticker, ex_date, pub_date, record_date, payable_date, raw_payload)
    assert row[0] == "AAPL"
    assert row[1] == "2026-02-07"
    assert row[4] == "2026-02-13"
    assert json.loads(row[5])["per_cash_div"] == 0.26


def test_backfill_splits_paginates_and_upserts():
    client = MagicMock()
    p1 = {"split_list": [{"ex_date": "2020-08-31", "split_base": 1, "split_ert": 4}], "next_key": "1"}
    p2 = {"split_list": [{"ex_date": "2014-06-09", "split_base": 1, "split_ert": 7}], "next_key": "-1"}
    client.call.side_effect = [p1, p2]
    with patch("futu_ingest.backfill_actions.get_conn") as mock_conn:
        cur = MagicMock()
        mock_conn.return_value.__enter__ = lambda s: mock_conn.return_value
        mock_conn.return_value.cursor.return_value.__enter__ = lambda s: cur
        n = backfill_splits(client, "AAPL")
    assert n == 2
    assert client.call.call_count == 2
    sql = cur.executemany.call_args[0][0]
    assert "INSERT INTO us_splits" in sql
