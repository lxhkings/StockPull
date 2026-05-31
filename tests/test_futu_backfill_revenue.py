import json
from unittest.mock import MagicMock, patch
from datetime import date

from futu_ingest.backfill_revenue import (
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
    with patch("futu_ingest.backfill_revenue.get_conn") as mock_conn:
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
    with patch("futu_ingest.backfill_revenue.get_conn") as mock_conn:
        cur = MagicMock()
        mock_conn.return_value.__enter__ = lambda s: mock_conn.return_value
        mock_conn.return_value.cursor.return_value.__enter__ = lambda s: cur
        n = backfill_earnings_move(client, "AAPL")
    assert n == 2
    sql = cur.executemany.call_args[0][0]
    assert "INSERT INTO us_earnings_price_move" in sql
