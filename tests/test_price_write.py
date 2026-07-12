"""modules.price_write 批写入测试。"""
from datetime import date
from unittest.mock import MagicMock

from modules.price_write import flush_prices_and_sync


def _mock_conn():
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cur
    conn.cursor.return_value.__exit__.return_value = False
    return conn, cur


def test_on_duplicate_mode_has_on_duplicate_key_update():
    """on_duplicate=True → prices SQL 含 ON DUPLICATE KEY UPDATE，commit 一次。"""
    conn, cur = _mock_conn()
    price_rows = [("600519.SH", date(2026, 5, 15), 100.0, 105.0, 99.0, 103.0, 1_000_000)]
    sync_rows = [("600519.SH", "price", date(2026, 5, 15), 1, "ok", "")]

    flush_prices_and_sync(conn, price_rows, sync_rows, on_duplicate=True)

    assert cur.executemany.call_count == 2
    prices_sql = cur.executemany.call_args_list[0][0][0]
    assert "ON DUPLICATE KEY UPDATE" in prices_sql
    assert "INSERT IGNORE" not in prices_sql
    assert "INTO prices " in prices_sql or "INTO prices\n" in prices_sql or "INTO prices (" in prices_sql
    conn.commit.assert_called_once()


def test_ignore_mode_has_insert_ignore():
    """on_duplicate=False → prices SQL 含 INSERT IGNORE，commit 一次。"""
    conn, cur = _mock_conn()
    price_rows = [("AAPL", date(2026, 5, 15), 100.0, 105.0, 99.0, 103.0, 1_000_000)]
    sync_rows = [("AAPL", "price", date(2026, 5, 15), 1, "ok", "")]

    flush_prices_and_sync(conn, price_rows, sync_rows, on_duplicate=False)

    assert cur.executemany.call_count == 2
    prices_sql = cur.executemany.call_args_list[0][0][0]
    assert "INSERT IGNORE" in prices_sql
    conn.commit.assert_called_once()


def test_empty_buffers_noop():
    """两侧 buffer 皆空：不写库、不 commit、不报错。"""
    conn, cur = _mock_conn()
    flush_prices_and_sync(conn, [], [], on_duplicate=True)
    conn.cursor.assert_not_called()
    conn.commit.assert_not_called()


def test_sync_only_still_commits_once():
    """仅 sync_rows：写 sync_log 并 commit 一次。"""
    conn, cur = _mock_conn()
    sync_rows = [("AAPL", "price", date.today(), 0, "error", "no data")]
    flush_prices_and_sync(conn, [], sync_rows, on_duplicate=True)
    assert cur.executemany.call_count == 1
    sync_sql = cur.executemany.call_args[0][0]
    assert "sync_log" in sync_sql
    conn.commit.assert_called_once()


def test_price_table_weekly():
    """price_table=prices_weekly 写入周线表。"""
    conn, cur = _mock_conn()
    price_rows = [("600519.SH", date(2026, 5, 15), 100.0, 105.0, 99.0, 103.0, 1_000_000)]
    flush_prices_and_sync(
        conn, price_rows, [], on_duplicate=True, price_table="prices_weekly"
    )
    prices_sql = cur.executemany.call_args[0][0]
    assert "prices_weekly" in prices_sql
    conn.commit.assert_called_once()
