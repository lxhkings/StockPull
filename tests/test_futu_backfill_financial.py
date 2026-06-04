import json
from unittest.mock import MagicMock, patch

from futu_ingest.backfill_financial import backfill_statement, STATEMENT_TABLES


def _fake_page():
    return {
        "report_list": [{
            "date_time_str": "2025-09-26",
            "fiscal_year": "2025",
            "financial_type": "7",
            "period_text": "2025/FY",
            "currency_code": "USD",
            "accounting_standards": "US_GAAP",
            "item_list": [{"field_id": 1, "data": 416161000000.0}],
        }],
        "next_key": "-1",
    }


def test_statement_tables_has_4_entries():
    assert len(STATEMENT_TABLES) == 4
    assert (1, "us_fin_income") in STATEMENT_TABLES


def test_backfill_statement_upserts_with_raw_payload():
    client = MagicMock()
    client.call.return_value = _fake_page()
    with patch("futu_ingest.backfill_financial.get_conn") as mock_conn:
        cur = MagicMock()
        mock_conn.return_value.__enter__ = lambda s: mock_conn.return_value
        mock_conn.return_value.cursor.return_value.__enter__ = lambda s: cur
        n, latest = backfill_statement(client, "AAPL", statement_type=1, table="us_fin_income")
    assert n == 1
    assert latest == "2025-09-26"
    sql = cur.executemany.call_args[0][0]
    assert "INSERT INTO us_fin_income" in sql
    assert "ON DUPLICATE KEY UPDATE" in sql
    row = cur.executemany.call_args[0][1][0]
    # row = (ticker, period_end, financial_type, fiscal_year, period_text,
    #        currency_code, accounting_standards, raw_payload)
    assert row[0] == "AAPL"
    assert row[1] == "2025-09-26"
    assert row[2] == "7"
    payload = json.loads(row[7])
    assert payload["item_list"][0]["data"] == 416161000000.0


def test_backfill_statement_paginates_until_minus_one():
    client = MagicMock()
    page1 = _fake_page(); page1["next_key"] = "10"
    page2 = _fake_page(); page2["next_key"] = "-1"
    client.call.side_effect = [page1, page2]
    with patch("futu_ingest.backfill_financial.get_conn") as mock_conn:
        cur = MagicMock()
        mock_conn.return_value.cursor.return_value.__enter__ = lambda s: cur
        backfill_statement(client, "AAPL", statement_type=1, table="us_fin_income")
    assert client.call.call_count == 2


def test_fin_sync_one_sums_4_statements():
    from futu_ingest.backfill_financial import fin_sync_one
    client = MagicMock()
    with patch("futu_ingest.backfill_financial.backfill_statement",
               return_value=(3, "2025-09-26")) as bs:
        total = fin_sync_one(client, "AAPL")
    assert total == 12          # 4 表 × 3
    assert bs.call_count == 4


def test_backfill_all_delegates_to_ticker_stream_with_data_type():
    from futu_ingest.backfill_financial import backfill_all
    with patch("futu_ingest.backfill_financial.get_client"), \
         patch("futu_ingest.backfill_financial.ticker_stream",
               return_value=(10, 1, 2)) as ts:
        rep = backfill_all(["AAPL", "MSFT", "GOOG"], force=True)
    assert rep == {"rows": 10, "tickers": 1, "skipped": 2}
    args = ts.call_args[0]
    assert args[3] == "us_financial"
    assert ts.call_args[1] == {"force": True} or args[4] is True
