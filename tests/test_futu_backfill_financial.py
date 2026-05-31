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
        n = backfill_statement(client, "AAPL", statement_type=1, table="us_fin_income")
    assert n == 1
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
