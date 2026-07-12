"""modules.sync_log 同步状态追踪测试。"""
from datetime import date
from unittest.mock import MagicMock


def test_upsert_sync_log_ok_updates_last_date():
    """ok 状态 upsert 更新 last_date。"""
    from modules.sync_log import _upsert_sync_log
    conn = MagicMock()
    _upsert_sync_log(conn, "AAPL", "price", date(2026, 1, 15), 100, "ok", "")
    conn.cursor.assert_called()
    conn.commit.assert_called_once()
    sql = conn.cursor.return_value.__enter__.return_value.execute.call_args[0][0]
    params = conn.cursor.return_value.__enter__.return_value.execute.call_args[0][1]
    assert "ON DUPLICATE KEY UPDATE" in sql
    assert params[:4] == ("AAPL", "price", date(2026, 1, 15), 100)
    assert params[4] == "ok"


def test_upsert_sync_log_error_preserves_last_date():
    """error 状态 upsert 不覆盖 last_date。"""
    from modules.sync_log import _upsert_sync_log
    conn = MagicMock()
    _upsert_sync_log(conn, "AAPL", "price", date.today(), 0, "error", "timeout")
    sql = conn.cursor.return_value.__enter__.return_value.execute.call_args[0][0]
    assert "IF(VALUES(status)='ok'" in sql  # error 不改 last_date


def test_get_last_sync_finds_ok_record():
    """sync_log 有 ok 记录时返回 last_date。"""
    from modules.sync_log import get_last_sync
    conn = MagicMock()
    cur = conn.cursor.return_value.__enter__.return_value
    cur.fetchone.return_value = [date(2026, 3, 1)]
    result = get_last_sync(conn, "AAPL", "price")
    assert result == date(2026, 3, 1)


def test_get_last_sync_falls_back_to_prices_table():
    """sync_log 无 ok 记录时 fallback 到 prices 表。"""
    from modules.sync_log import get_last_sync
    conn = MagicMock()
    cur = conn.cursor.return_value.__enter__.return_value
    cur.fetchone.side_effect = [None, [date(2026, 2, 15)]]
    result = get_last_sync(conn, "MSFT", "price")
    assert result == date(2026, 2, 15)


def test_set_sync_error_truncates_long_message():
    """error message 超过 500 字符时截断。"""
    from modules.sync_log import set_sync_error
    conn = MagicMock()
    long_msg = "x" * 600
    set_sync_error(conn, "AAPL", "price", long_msg)
    params = conn.cursor.return_value.__enter__.return_value.execute.call_args[0][1]
    assert len(params[5]) <= 500  # message 被截断


def test_get_last_sync_map_empty_tickers():
    """空列表直接返回 {}，不查库。"""
    from modules.sync_log import get_last_sync_map
    conn = MagicMock()
    assert get_last_sync_map(conn, [], "price") == {}
    conn.cursor.assert_not_called()


def test_get_last_sync_map_ok_hits():
    """sync_log ok 命中写入 map，未命中为 None。"""
    from modules.sync_log import get_last_sync_map
    conn = MagicMock()
    cur = conn.cursor.return_value.__enter__.return_value
    cur.fetchall.return_value = [
        ("AAPL", date(2026, 3, 1)),
        ("MSFT", date(2026, 3, 2)),
    ]
    result = get_last_sync_map(conn, ["AAPL", "MSFT", "GOOG"], "price")
    assert result == {
        "AAPL": date(2026, 3, 1),
        "MSFT": date(2026, 3, 2),
        "GOOG": None,
    }
    # data_type=price 且有 missing，会再查 prices
    assert cur.execute.call_count == 2


def test_get_last_sync_map_missing_none_non_price():
    """非 price data_type：无 ok 记录则为 None，不查 prices。"""
    from modules.sync_log import get_last_sync_map
    conn = MagicMock()
    cur = conn.cursor.return_value.__enter__.return_value
    cur.fetchall.return_value = [("AAPL", date(2026, 3, 1))]
    result = get_last_sync_map(conn, ["AAPL", "MSFT"], "price_weekly")
    assert result == {"AAPL": date(2026, 3, 1), "MSFT": None}
    assert cur.execute.call_count == 1


def test_get_last_sync_map_price_fallback():
    """price：sync_log 无 ok 时 fallback prices MAX(date)。"""
    from modules.sync_log import get_last_sync_map
    conn = MagicMock()
    cur = conn.cursor.return_value.__enter__.return_value
    cur.fetchall.side_effect = [
        [("AAPL", date(2026, 3, 1))],  # sync_log
        [("MSFT", date(2026, 2, 15)), ("GOOG", None)],  # prices for missing
    ]
    result = get_last_sync_map(conn, ["AAPL", "MSFT", "GOOG", "AMZN"], "price")
    assert result == {
        "AAPL": date(2026, 3, 1),
        "MSFT": date(2026, 2, 15),
        "GOOG": None,
        "AMZN": None,
    }
    # second SQL targets missing only
    second_sql, second_params = cur.execute.call_args_list[1][0]
    assert "FROM prices" in second_sql
    assert second_params == ("MSFT", "GOOG", "AMZN")
