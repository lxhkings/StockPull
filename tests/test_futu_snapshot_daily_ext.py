import json
from unittest.mock import MagicMock, patch
from datetime import date

from futu_ingest.snapshot_daily_ext import (
    snapshot_capital_flow, snapshot_capital_dist,
    snapshot_short_interest, snapshot_short_volume
)


def _fake_capital_flow():
    return [
        {"date": "2026-05-30", "in_flow": 1500000, "super_in_flow": 800000,
         "big_in_flow": 400000, "mid_in_flow": 200000, "sml_in_flow": 100000,
         "main_in_flow": 1200000},
        {"date": "2026-05-29", "in_flow": -500000, "super_in_flow": -300000},
    ]


def _fake_capital_dist():
    return {
        "capital_in_super": 5000000, "capital_in_big": 3000000,
        "capital_in_mid": 2000000, "capital_in_small": 1000000,
        "capital_out_super": 4000000, "capital_out_big": 2500000,
        "capital_out_mid": 1800000, "capital_out_small": 900000,
        "date": "2026-05-30",
    }


def _fake_short_interest():
    return [
        {"timestamp": "2026-05-30", "shares_short": 95000000, "short_percent": 0.65,
         "avg_daily_share_volume": 50000000, "days_to_cover": 1.9,
         "close_price": 185.0, "last_close_price": 183.0},
    ]


def _fake_short_volume():
    return [
        {"timestamp": "2026-05-30", "total_shares_short": 25000000,
         "nasdaq_shares_short": 15000000, "nyse_shares_short": 10000000,
         "short_percent": 0.30, "volume": 80000000,
         "close_price": 185.0, "last_close_price": 183.0, "daily_trade_avg_ratio": 0.31},
    ]


def test_snapshot_capital_flow_upserts():
    client = MagicMock()
    client.call.return_value = _fake_capital_flow()
    with patch("futu_ingest.snapshot_daily_ext.get_conn") as mock_conn:
        cur = MagicMock()
        mock_conn.return_value.__enter__ = lambda s: mock_conn.return_value
        mock_conn.return_value.cursor.return_value.__enter__ = lambda s: cur
        n = snapshot_capital_flow(client, "AAPL")
    assert n == 2
    sql = cur.executemany.call_args[0][0]
    assert "INSERT INTO us_capital_flow" in sql


def test_snapshot_short_interest_handles_3_value_return():
    """short_interest 返回 3 值，client 已适配。"""
    client = MagicMock()
    client.call.return_value = _fake_short_interest()
    with patch("futu_ingest.snapshot_daily_ext.get_conn") as mock_conn:
        cur = MagicMock()
        mock_conn.return_value.__enter__ = lambda s: mock_conn.return_value
        mock_conn.return_value.cursor.return_value.__enter__ = lambda s: cur
        n = snapshot_short_interest(client, "AAPL")
    assert n == 1
    sql = cur.executemany.call_args[0][0]
    assert "INSERT INTO us_short_interest" in sql
