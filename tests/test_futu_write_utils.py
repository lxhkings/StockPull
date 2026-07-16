from unittest.mock import MagicMock, patch


def test_upsert_rows_builds_odku_and_commits():
    from apis.futu.write_utils import upsert_rows

    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value.__enter__ = lambda s: mock_cur
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

    rows = [("AAPL", "x", "1")]
    with patch("apis.futu.write_utils.get_conn") as g:
        g.return_value.__enter__ = lambda s: mock_conn
        g.return_value.__exit__ = MagicMock(return_value=False)
        n = upsert_rows(
            "us_company_profile",
            ["ticker", "field_name", "field_value"],
            rows,
            ["field_value"],
            ticker="AAPL",
        )
    assert n == 1
    sql = mock_cur.executemany.call_args[0][0]
    assert "INSERT INTO us_company_profile" in sql
    assert "ON DUPLICATE KEY UPDATE" in sql
    assert "field_value=VALUES(field_value)" in sql
    mock_conn.commit.assert_called_once()


def test_upsert_rows_empty_returns_zero():
    from apis.futu.write_utils import upsert_rows
    assert upsert_rows("t", ["a"], [], ["a"]) == 0


def test_paginate_call_stops_on_empty_or_sentinel():
    from apis.futu.write_utils import paginate_call

    client = MagicMock()
    client.call.side_effect = [
        {"item_list": [{"id": 1}], "next_key": "abc"},
        {"item_list": [{"id": 2}], "next_key": "-1"},
    ]
    items = paginate_call(
        client, "get_foo", "US.AAPL", list_key="item_list", page_num=50
    )
    assert [i["id"] for i in items] == [1, 2]
    assert client.call.call_count == 2
