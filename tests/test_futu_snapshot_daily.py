import json
import pandas as pd
from datetime import date
from unittest.mock import MagicMock, patch

from futu_ingest.snapshot_daily import snapshot_shares, snapshot_analyst


def test_snapshot_shares_upserts_today():
    client = MagicMock()
    client.call.return_value = pd.DataFrame({
        "code": ["US.AAPL"],
        "issued_shares": [14687356000],
        "outstanding_shares": [14642591784],
        "total_market_val": [4583336313360.0],
        "circular_market_val": [4569367192115.04],
    })
    with patch("futu_ingest.snapshot_daily.get_conn") as mock_conn:
        cur = MagicMock()
        mock_conn.return_value.__enter__ = lambda s: mock_conn.return_value
        mock_conn.return_value.cursor.return_value.__enter__ = lambda s: cur
        n = snapshot_shares(client, ["AAPL"])
    assert n == 1
    sql = cur.executemany.call_args[0][0]
    assert "INSERT INTO us_shares_daily" in sql
    row = cur.executemany.call_args[0][1][0]
    # row = (ticker, date, issued, outstanding, total_mv, circular_mv, raw_payload)
    assert row[0] == "AAPL"
    assert row[1] == date.today().isoformat()
    assert row[3] == 14642591784


def test_snapshot_analyst_upserts_today():
    client = MagicMock()
    client.call.return_value = {
        "highest": 400.0, "average": 323.63, "lowest": 253.0,
        "rating": "买入", "total": 27, "buy": 62.96, "hold": 33.33, "sell": 3.70,
    }
    with patch("futu_ingest.snapshot_daily.get_conn") as mock_conn:
        cur = MagicMock()
        mock_conn.return_value.__enter__ = lambda s: mock_conn.return_value
        mock_conn.return_value.cursor.return_value.__enter__ = lambda s: cur
        n = snapshot_analyst(client, "AAPL")
    assert n == 1
    sql = cur.execute.call_args[0][0]
    assert "INSERT INTO us_analyst_consensus" in sql
    params = cur.execute.call_args[0][1]
    # (ticker, snapshot_date, target_high, target_avg, target_low,
    #  rating, total, buy, hold, sell, raw_payload)
    assert params[0] == "AAPL"
    assert params[2] == 400.0
    assert params[6] == 27


def test_run_daily_aggregates_via_streams(monkeypatch):
    import futu_ingest.snapshot_daily as m
    monkeypatch.setattr(m, "get_client", lambda: object())
    monkeypatch.setattr(m, "snapshot_shares", lambda c, ts: 100)
    monkeypatch.setattr(m, "snapshot_analyst", lambda c, t: 1)
    rep = m.run_daily(["A", "B", "C"])
    assert rep == {"shares": 100, "analyst": 3, "tickers": 3}
