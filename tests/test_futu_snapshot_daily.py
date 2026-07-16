import pandas as pd
from datetime import date
from unittest.mock import MagicMock, patch

from apis.futu.snapshot_daily import snapshot_shares, snapshot_analyst


def test_snapshot_shares_upserts_today():
    client = MagicMock()
    client.call.return_value = pd.DataFrame({
        "code": ["US.AAPL"],
        "issued_shares": [14687356000],
        "outstanding_shares": [14642591784],
        "total_market_val": [4583336313360.0],
        "circular_market_val": [4569367192115.04],
    })
    with patch("apis.futu.write_utils.get_conn") as mock_conn:
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
    with patch("apis.futu.write_utils.get_conn") as mock_conn:
        cur = MagicMock()
        mock_conn.return_value.__enter__ = lambda s: mock_conn.return_value
        mock_conn.return_value.cursor.return_value.__enter__ = lambda s: cur
        n = snapshot_analyst(client, "AAPL")
    assert n == 1
    sql = cur.executemany.call_args[0][0]
    assert "INSERT INTO us_analyst_consensus" in sql
    params = cur.executemany.call_args[0][1][0]
    # (ticker, snapshot_date, target_high, target_avg, target_low,
    #  rating, total, buy, hold, sell, raw_payload)
    assert params[0] == "AAPL"
    assert params[2] == 400.0
    assert params[6] == 27


def test_run_daily_aggregates_via_streams(monkeypatch):
    import apis.futu.snapshot_daily as m
    import apis.futu.concurrency as conc
    monkeypatch.setattr(m, "get_client", lambda: object())
    monkeypatch.setattr(m, "snapshot_shares", lambda c, ts: 100)
    monkeypatch.setattr(m, "snapshot_analyst", lambda c, t: 1)
    monkeypatch.setattr(m, "fresh_tickers", lambda dt, rd: set())
    monkeypatch.setattr(m, "mark_ok", lambda t, dt, n: None)
    monkeypatch.setattr(conc, "fresh_tickers", lambda dt, rd: set())
    monkeypatch.setattr(conc, "mark_ok", lambda t, dt, n: None)
    monkeypatch.setattr(conc, "mark_error", lambda t, dt, msg: None)
    rep = m.run_daily(["A", "B", "C"])
    assert rep == {"shares": 100, "analyst": 3, "skipped": 0, "tickers": 3}


def test_sync_shares_skips_when_sentinel_fresh():
    from unittest.mock import MagicMock, patch
    from apis.futu.snapshot_daily import sync_shares
    client = MagicMock()
    with patch("apis.futu.snapshot_daily.fresh_tickers", return_value={"__ALL__"}), \
         patch("apis.futu.snapshot_daily.snapshot_shares") as ss:
        rows, ok, skipped = sync_shares(client, ["AAPL"], force=False)
    ss.assert_not_called()
    assert (rows, ok, skipped) == (0, 0, 1)


def test_sync_shares_pulls_and_marks_when_stale():
    from unittest.mock import MagicMock, patch
    from apis.futu.snapshot_daily import sync_shares
    client = MagicMock()
    with patch("apis.futu.snapshot_daily.fresh_tickers", return_value=set()), \
         patch("apis.futu.snapshot_daily.snapshot_shares", return_value=42), \
         patch("apis.futu.snapshot_daily.mark_ok") as mok:
        rows, ok, skipped = sync_shares(client, ["AAPL"], force=False)
    assert (rows, ok, skipped) == (42, 1, 0)
    mok.assert_called_once_with("__ALL__", "us_shares_daily", 42)


def test_sync_shares_force_pulls():
    from unittest.mock import MagicMock, patch
    from apis.futu.snapshot_daily import sync_shares
    client = MagicMock()
    with patch("apis.futu.snapshot_daily.fresh_tickers") as ft, \
         patch("apis.futu.snapshot_daily.snapshot_shares", return_value=1), \
         patch("apis.futu.snapshot_daily.mark_ok"):
        sync_shares(client, ["AAPL"], force=True)
    ft.assert_not_called()


def test_run_daily_threads_force_to_analyst():
    from unittest.mock import patch
    from apis.futu.snapshot_daily import run_daily as daily_run
    captured = {}

    def fake_ts(fn, client, tickers, data_type, force=False):
        captured["analyst"] = (data_type, force)
        return (1, 1, 0)

    with patch("apis.futu.snapshot_daily.get_client"), \
         patch("apis.futu.snapshot_daily.ticker_stream", side_effect=fake_ts), \
         patch("apis.futu.snapshot_daily.sync_shares", return_value=(2, 1, 0)):
        rep = daily_run(["AAPL"], force=True)
    assert captured["analyst"] == ("us_analyst_consensus", True)
    assert rep["shares"] == 2 and rep["analyst"] == 1
