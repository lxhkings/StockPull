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
