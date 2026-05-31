from unittest.mock import MagicMock, patch

from futu_ingest.backfill_profile import backfill_profile


def _fake_profile():
    return [
        {"field_name": "CEO", "field_value": "Tim Cook", "field_type": "text"},
        {"field_name": "Market", "field_value": "NASDAQ", "field_type": "text"},
        {"field_name": "Employees", "field_value": "164000", "field_type": "number"},
    ]


def test_backfill_profile_upserts():
    client = MagicMock()
    client.call.return_value = _fake_profile()
    with patch("futu_ingest.backfill_profile.get_conn") as mock_conn:
        cur = MagicMock()
        mock_conn.return_value.__enter__ = lambda s: mock_conn.return_value
        mock_conn.return_value.cursor.return_value.__enter__ = lambda s: cur
        n = backfill_profile(client, "AAPL")
    assert n == 3
    sql = cur.executemany.call_args[0][0]
    assert "INSERT INTO us_company_profile" in sql
    assert "ON DUPLICATE KEY UPDATE" in sql
    rows = cur.executemany.call_args[0][1]
    assert rows[0][0] == "AAPL"
    assert rows[0][1] == "CEO"
    assert rows[0][2] == "Tim Cook"


def test_backfill_profile_skips_empty():
    client = MagicMock()
    client.call.return_value = None
    with patch("futu_ingest.backfill_profile.get_conn"):
        n = backfill_profile(client, "AAPL")
    assert n == 0
