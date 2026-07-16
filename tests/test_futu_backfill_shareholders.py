from unittest.mock import MagicMock, patch

from apis.futu.backfill_shareholders import (
    backfill_overview, backfill_holding_changes,
    backfill_institutional, backfill_insider_holders, backfill_insider_trades
)


def _fake_overview():
    return {
        "main_holder": [
            {"holder_name": "Vanguard", "holder_pct": 8.5, "holder_id": 12345},
            {"holder_name": "BlackRock", "holder_pct": 7.2, "holder_id": 12346},
        ],
        "holder_type": [
            {"holder_name": "Mutual Fund", "holder_pct": 45.0},
            {"holder_name": "ETF", "holder_pct": 25.0},
        ],
        "holding_period": ["2026/Q2", "2026/Q1"],
    }


def _fake_holding_changes():
    return [
        {"holder_id": 12345, "holder_name": "Vanguard", "holder_type": "Mutual Fund",
         "share_change_num": 5000000, "share_ratio": 8.5, "period_text": "2026/Q2"},
    ]


def _fake_institutional():
    return {
        "institution_quantity": 3500,
        "holder_quantity": 8500000000,
        "holder_pct": 85.0,
        "period_text": "2026/Q2",
    }


def _fake_insider_holders():
    return [
        {"holder_id": 99999, "holder_name": "Tim Cook", "title": "CEO",
         "holder_quantity": 3000000, "holder_pct": 0.02},
    ]


def _fake_insider_trades():
    return [
        {"holder_id": 99999, "holder_name": "Tim Cook", "title": "CEO",
         "min_trade_date": "2026-05-15", "transaction_type": "Sale",
         "trade_shares": -50000, "min_price": 180.0, "max_price": 182.0},
    ]


def test_backfill_overview_merges_main_and_type():
    client = MagicMock()
    client.call.return_value = _fake_overview()
    with patch("apis.futu.write_utils.get_conn") as mock_conn:
        cur = MagicMock()
        mock_conn.return_value.__enter__ = lambda s: mock_conn.return_value
        mock_conn.return_value.cursor.return_value.__enter__ = lambda s: cur
        n = backfill_overview(client, "AAPL")
    assert n == 4  # 2 main + 2 type
    sql = cur.executemany.call_args[0][0]
    assert "INSERT INTO us_shareholders_overview" in sql


def test_backfill_insider_trades_upserts():
    client = MagicMock()
    client.call.return_value = _fake_insider_trades()
    with patch("apis.futu.write_utils.get_conn") as mock_conn:
        cur = MagicMock()
        mock_conn.return_value.__enter__ = lambda s: mock_conn.return_value
        mock_conn.return_value.cursor.return_value.__enter__ = lambda s: cur
        n = backfill_insider_trades(client, "AAPL")
    assert n == 1
    sql = cur.executemany.call_args[0][0]
    assert "INSERT INTO us_insider_trades" in sql


def test_backfill_holding_changes_upserts():
    client = MagicMock()
    client.call.return_value = _fake_holding_changes()
    with patch("apis.futu.write_utils.get_conn") as mock_conn:
        cur = MagicMock()
        mock_conn.return_value.__enter__ = lambda s: mock_conn.return_value
        mock_conn.return_value.cursor.return_value.__enter__ = lambda s: cur
        n = backfill_holding_changes(client, "AAPL")
    assert n == 1
    sql = cur.executemany.call_args[0][0]
    assert "INSERT INTO us_holding_changes" in sql


def test_backfill_institutional_upserts():
    client = MagicMock()
    client.call.return_value = _fake_institutional()
    with patch("apis.futu.write_utils.get_conn") as mock_conn:
        cur = MagicMock()
        mock_conn.return_value.__enter__ = lambda s: mock_conn.return_value
        mock_conn.return_value.cursor.return_value.__enter__ = lambda s: cur
        n = backfill_institutional(client, "AAPL")
    assert n == 1
    sql = cur.executemany.call_args[0][0]
    assert "INSERT INTO us_institutional" in sql


def test_backfill_insider_holders_upserts():
    client = MagicMock()
    client.call.return_value = _fake_insider_holders()
    with patch("apis.futu.write_utils.get_conn") as mock_conn:
        cur = MagicMock()
        mock_conn.return_value.__enter__ = lambda s: mock_conn.return_value
        mock_conn.return_value.cursor.return_value.__enter__ = lambda s: cur
        n = backfill_insider_holders(client, "AAPL")
    assert n == 1
    sql = cur.executemany.call_args[0][0]
    assert "INSERT INTO us_insider_holders" in sql


def test_backfill_overview_returns_0_on_empty():
    client = MagicMock()
    client.call.return_value = {}
    with patch("apis.futu.write_utils.get_conn"):
        n = backfill_overview(client, "AAPL")
    assert n == 0


def test_backfill_insider_trades_returns_0_on_empty():
    client = MagicMock()
    client.call.return_value = []
    with patch("apis.futu.write_utils.get_conn"):
        n = backfill_insider_trades(client, "AAPL")
    assert n == 0


def test_backfill_all_aggregates_via_streams(monkeypatch):
    import apis.futu.backfill_shareholders as m

    def fake_ts(fn, client, tickers, data_type, force=False):
        n = fn(client, tickers[0]) if tickers else 0
        return (n * len(tickers), len(tickers), 0)

    monkeypatch.setattr(m, "get_client", lambda: object())
    monkeypatch.setattr(m, "ticker_stream", fake_ts)
    monkeypatch.setattr(m, "backfill_overview", lambda c, t: 1)
    monkeypatch.setattr(m, "backfill_holding_changes", lambda c, t: 2)
    monkeypatch.setattr(m, "backfill_institutional", lambda c, t: 3)
    monkeypatch.setattr(m, "backfill_insider_holders", lambda c, t: 4)
    monkeypatch.setattr(m, "backfill_insider_trades", lambda c, t: 5)
    rep = m.backfill_all(["A", "B"])
    assert rep == {
        "overview_rows": 2, "changes_rows": 4, "institutional_rows": 6,
        "insider_holders_rows": 8, "insider_trades_rows": 10,
        "skipped": 0, "tickers": 2,
    }


def test_shareholders_backfill_all_passes_5_data_types():
    """验证 backfill_all 正确传递 5 个 data_type 和 force 参数到 ticker_stream。"""
    from apis.futu.backfill_shareholders import backfill_all as sh_all

    captured = []

    def fake_ts(fn, client, tickers, data_type, force=False):
        captured.append(data_type)
        return (1, 1, 0)

    with patch("apis.futu.backfill_shareholders.get_client"), \
         patch("apis.futu.backfill_shareholders.ticker_stream", side_effect=fake_ts):
        rep = sh_all(["AAPL"], force=True)
    assert set(captured) == {
        "us_shareholders_overview", "us_holding_changes", "us_institutional",
        "us_insider_holders", "us_insider_trades",
    }
    assert rep["tickers"] == 1
