import json
import pandas as pd
from unittest.mock import MagicMock, patch

from futu_ingest.backfill_earnings import backfill_earnings, PIT_BACKFILL_SQL


def test_backfill_earnings_upserts_pub_date():
    client = MagicMock()
    client.call.return_value = pd.DataFrame({
        "period_text": ["2026/Q2"],
        "fiscal_year": ["2026"],
        "financial_type": ["2"],
        "pub_time_str": ["2026-04-30 17:00:00"],
        "pub_trading_day_str": ["2026-04-30"],
    })
    with patch("futu_ingest.backfill_earnings.get_conn") as mock_conn:
        cur = MagicMock()
        mock_conn.return_value.__enter__ = lambda s: mock_conn.return_value
        mock_conn.return_value.cursor.return_value.__enter__ = lambda s: cur
        n = backfill_earnings(client, "AAPL")
    assert n == 1
    row = cur.executemany.call_args[0][1][0]
    # row = (ticker, period_text, fiscal_year, financial_type, pub_date, raw_payload)
    assert row[0] == "AAPL"
    assert row[1] == "2026/Q2"
    assert row[4] == "2026-04-30"     # pub_date 取日期部分
    payload = json.loads(row[5])
    assert payload["pub_time_str"] == "2026-04-30 17:00:00"


def test_pit_backfill_sql_targets_all_4_tables():
    # 4 张财务表都要回填 ann_date
    for tbl in ("us_fin_income", "us_fin_balance", "us_fin_cashflow", "us_fin_indicator"):
        assert tbl in PIT_BACKFILL_SQL


from futu_ingest.backfill_earnings import backfill_all as earnings_all


def test_earnings_backfill_all_uses_ticker_stream_then_pit():
    with patch("futu_ingest.backfill_earnings.get_client"), \
         patch("futu_ingest.backfill_earnings.ticker_stream",
               return_value=(9, 1, 1)) as ts, \
         patch("futu_ingest.backfill_earnings.run_pit_backfill",
               return_value={"us_fin_income": 3}) as pit:
        rep = earnings_all(["AAPL", "MSFT"], force=True)
    assert ts.call_args[0][3] == "us_earnings_dates"
    assert rep["earnings_rows"] == 9
    assert rep["skipped"] == 1
    assert rep["pit"] == {"us_fin_income": 3}
    pit.assert_called_once()
