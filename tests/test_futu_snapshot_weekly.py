import json
from unittest.mock import MagicMock, patch
from datetime import date

from futu_ingest.snapshot_weekly import (
    snapshot_valuation, snapshot_rating, snapshot_morningstar
)


def _fake_valuation():
    return {
        "trend": {"current_value": 28.5, "average_value": 25.0, "valuation_type": "PE_TTM"},
        "market_distribution": {"sections": [{"start": 10, "end": 20, "number": 100}]},
        "plate_distribution": {"plate": "T", "plate_name": "Technology", "plate_ranking": 5},
        "profit_growth_rate": {"financial_ttm_multiple": 1.15},
    }


def _fake_rating():
    return {
        "inst_rating_summary_list": [
            {"institution_uid": "uid1", "institution_name": "Goldman Sachs",
             "rating": "Buy", "target_price": 200.0, "update_time": "2026-05-30"},
            {"institution_uid": "uid2", "institution_name": "Morgan Stanley",
             "rating": "Hold", "target_price": 180.0, "update_time": "2026-05-28"},
        ],
        "next_key": "-1",
    }


def _fake_morningstar():
    return {
        "star_rating": 4,
        "fair_value": 195.0,
        "economic_moat_label": "宽",
        "uncertainty_label": "中等",
        "capital_allocation_label": "优秀",
        "analyst_report_by_line": "John Doe, CFA",
        "bull_say": ["Strong ecosystem"],
        "bear_say": ["Valuation stretched"],
        "investment_thesis_content": "Apple continues to...",
    }


def test_snapshot_valuation_extracts_key_fields():
    client = MagicMock()
    client.call.return_value = _fake_valuation()
    with patch("futu_ingest.snapshot_weekly.get_conn") as mock_conn:
        cur = MagicMock()
        mock_conn.return_value.__enter__ = lambda s: mock_conn.return_value
        mock_conn.return_value.cursor.return_value.__enter__ = lambda s: cur
        n = snapshot_valuation(client, "AAPL")
    assert n == 1
    sql = cur.execute.call_args[0][0]
    assert "INSERT INTO us_valuation_snapshot" in sql
    params = cur.execute.call_args[0][1]
    assert params[0] == "AAPL"
    assert params[2] == 28.5  # pe_ttm


def test_snapshot_rating_paginates():
    client = MagicMock()
    page1 = _fake_rating()
    page1["next_key"] = "10"
    page2 = _fake_rating()
    page2["next_key"] = "-1"
    client.call.side_effect = [page1, page2]
    with patch("futu_ingest.snapshot_weekly.get_conn") as mock_conn:
        cur = MagicMock()
        mock_conn.return_value.__enter__ = lambda s: mock_conn.return_value
        mock_conn.return_value.cursor.return_value.__enter__ = lambda s: cur
        n = snapshot_rating(client, "AAPL")
    assert n == 4  # 2 + 2
    assert client.call.call_count == 2


def test_snapshot_morningstar_upserts():
    client = MagicMock()
    client.call.return_value = _fake_morningstar()
    with patch("futu_ingest.snapshot_weekly.get_conn") as mock_conn:
        cur = MagicMock()
        mock_conn.return_value.__enter__ = lambda s: mock_conn.return_value
        mock_conn.return_value.cursor.return_value.__enter__ = lambda s: cur
        n = snapshot_morningstar(client, "AAPL")
    assert n == 1
    sql = cur.execute.call_args[0][0]
    assert "INSERT INTO us_morningstar" in sql
    params = cur.execute.call_args[0][1]
    assert params[2] == 4  # star_rating
    assert params[4] == 195.0  # fair_value
