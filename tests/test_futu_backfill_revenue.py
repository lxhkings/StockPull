from unittest.mock import MagicMock, patch

from apis.futu.backfill_revenue import (
    backfill_revenue, backfill_earnings_move, RECENT_PERIODS
)


def _fake_revenue():
    return {
        "breakdown_list": [{
            "type": 8,
            "item_list": [
                {"name": "iPhone", "main_oper_income": 51000000000, "ratio": 52.3},
                {"name": "Services", "main_oper_income": 22000000000, "ratio": 22.6},
            ]
        }],
        "screen_date_list": [
            {"date": 1714521600, "financial_type": 8, "period_text": "2026/Q2"},
            {"date": 1704067200, "financial_type": 8, "period_text": "2026/Q1"},
        ]
    }


def _fake_earnings_move():
    return [
        {"period_text": "2026/Q2", "day_offset": -2, "trading_day": "2026-05-01",
         "open": 170.0, "close": 175.0, "volume": 50000000},
        {"period_text": "2026/Q2", "day_offset": 0, "trading_day": "2026-05-03",
         "open": 172.0, "close": 180.0, "volume": 80000000},
    ]


def test_backfill_revenue_limits_periods():
    """应限制近 N 期，避免全量 71 期。"""
    client = MagicMock()
    client.call.return_value = _fake_revenue()
    with patch("apis.futu.write_utils.get_conn") as mock_conn:
        cur = MagicMock()
        mock_conn.return_value.__enter__ = lambda s: mock_conn.return_value
        mock_conn.return_value.cursor.return_value.__enter__ = lambda s: cur
        n = backfill_revenue(client, "AAPL")
    # 首次 + 逐期回填（限近 RECENT_PERIODS 期）
    assert client.call.call_count <= RECENT_PERIODS + 1
    assert n > 0


def test_backfill_earnings_move_upserts():
    client = MagicMock()
    client.call.return_value = _fake_earnings_move()
    with patch("apis.futu.write_utils.get_conn") as mock_conn:
        cur = MagicMock()
        mock_conn.return_value.__enter__ = lambda s: mock_conn.return_value
        mock_conn.return_value.cursor.return_value.__enter__ = lambda s: cur
        n = backfill_earnings_move(client, "AAPL")
    assert n == 2
    sql = cur.executemany.call_args[0][0]
    assert "INSERT INTO us_earnings_price_move" in sql


def test_backfill_all_aggregates_via_streams(monkeypatch):
    import apis.futu.backfill_revenue as m

    def fake_ts(fn, client, tickers, data_type, force=False):
        n = fn(client, tickers[0]) if tickers else 0
        return (n * len(tickers), len(tickers), 0)

    monkeypatch.setattr(m, "get_client", lambda: object())
    monkeypatch.setattr(m, "ticker_stream", fake_ts)
    monkeypatch.setattr(m, "backfill_revenue", lambda c, t: 7)
    monkeypatch.setattr(m, "backfill_earnings_move", lambda c, t: 11)
    rep = m.backfill_all(["A", "B"])
    assert rep == {"revenue_rows": 14, "earnings_move_rows": 22, "skipped": 0, "tickers": 2}


def test_revenue_backfill_all_passes_data_types():
    """验证 backfill_all 正确传递 data_type 和 force 参数到 ticker_stream。"""
    from apis.futu.backfill_revenue import backfill_all as revenue_all

    captured = []

    def fake_ts(fn, client, tickers, data_type, force=False):
        captured.append((data_type, force))
        return (6, 3, 1)

    with patch("apis.futu.backfill_revenue.get_client"), \
         patch("apis.futu.backfill_revenue.ticker_stream", side_effect=fake_ts):
        rep = revenue_all(["AAPL"], force=False)
    assert ("us_revenue_breakdown", False) in captured
    assert ("us_earnings_price_move", False) in captured
    assert rep["revenue_rows"] == 6 and rep["earnings_move_rows"] == 6
