from unittest.mock import MagicMock, patch

from futu_ingest.backfill_efficiency import backfill_efficiency


def _fake_efficiency():
    return {
        "item_list": [
            {
                "fiscal_year": 2025, "financial_type": 7, "period_text": "2025/FY",
                "end_date": "2025-09-26", "employee_num": 164000,
                "employee_num_yoy": 0.03, "income_per_capita": 2500000,
                "income_per_capita_yoy": 0.08, "profit_per_capita": 600000,
                "profit_per_capita_yoy": 0.12, "net_profit_per_capita": 550000,
                "net_profit_per_capita_yoy": 0.11,
            },
            {
                "fiscal_year": 2024, "financial_type": 7, "period_text": "2024/FY",
                "end_date": "2024-09-27", "employee_num": 160000,
                "income_per_capita": 2300000,
            },
        ],
        "currency_code": "USD",
    }


def test_backfill_efficiency_upserts():
    client = MagicMock()
    client.call.return_value = _fake_efficiency()
    with patch("futu_ingest.backfill_efficiency.get_conn") as mock_conn:
        cur = MagicMock()
        mock_conn.return_value.__enter__ = lambda s: mock_conn.return_value
        mock_conn.return_value.cursor.return_value.__enter__ = lambda s: cur
        n = backfill_efficiency(client, "AAPL")
    assert n == 2
    sql = cur.executemany.call_args[0][0]
    assert "INSERT INTO us_op_efficiency" in sql
    assert "ON DUPLICATE KEY UPDATE" in sql
    rows = cur.executemany.call_args[0][1]
    assert rows[0][0] == "AAPL"
    assert rows[0][1] == "2025/FY"
    assert rows[0][3] == 164000  # employee_num


from futu_ingest.backfill_efficiency import backfill_all as eff_all


def test_efficiency_backfill_all_uses_ticker_stream():
    with patch("futu_ingest.backfill_efficiency.get_client"), \
         patch("futu_ingest.backfill_efficiency.ticker_stream",
               return_value=(7, 2, 0)) as ts:
        rep = eff_all(["AAPL", "MSFT"], force=False)
    assert rep == {"rows": 7, "tickers": 2, "skipped": 0}
    assert ts.call_args[0][3] == "us_op_efficiency"
