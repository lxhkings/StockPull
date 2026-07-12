"""modules.db_admin 管理查询测试。"""
from unittest.mock import patch


def test_get_index_tickers_returns_ticker_list():
    """get_index_tickers 返回最新快照的成分股列表。"""
    from modules.db_admin import get_index_tickers
    with patch("modules.db_admin.query", return_value=[
        {"ticker": "AAPL"}, {"ticker": "MSFT"}
    ]):
        result = get_index_tickers("SP500")
    assert result == ["AAPL", "MSFT"]


def test_create_prices_intraday_table_executes_ddl():
    """create_prices_intraday_table 执行 CREATE TABLE IF NOT EXISTS。"""
    from modules.db_admin import create_prices_intraday_table
    with patch("modules.db_admin.execute") as mock_exec:
        create_prices_intraday_table()
    mock_exec.assert_called_once()
    sql = mock_exec.call_args[0][0]
    assert "CREATE TABLE IF NOT EXISTS prices_intraday" in sql


def test_show_status_connects_and_prints(capsys):
    """show_status 查询统计信息并打印。"""
    from modules.db_admin import show_status

    class FakeCursor:
        def execute(self, sql, params=None): pass
        def fetchone(self):
            return [100]
        def __enter__(self): return self
        def __exit__(self, *a): pass

    class FakeConn:
        def cursor(self):
            return FakeCursor()
        def close(self): pass

    with patch("modules.db_admin.get_conn", return_value=FakeConn()):
        show_status()
    captured = capsys.readouterr()
    assert "股票总数" in captured.out
    assert "100" in captured.out


def test_show_status_includes_fundamental_table_row_estimates(capsys):
    """show_status 附带基本面表(财务/估值/股东回报)的近似行数。"""
    from modules.db_admin import show_status

    class FakeCursor:
        def execute(self, sql, params=None): pass
        def fetchone(self):
            return [42]
        def __enter__(self): return self
        def __exit__(self, *a): pass

    class FakeConn:
        def cursor(self):
            return FakeCursor()
        def close(self): pass

    with patch("modules.db_admin.get_conn", return_value=FakeConn()):
        show_status()
    captured = capsys.readouterr()
    assert "fin_income=42" in captured.out
    assert "cn_valuation_snapshot=42" in captured.out
    assert "dividend=42" in captured.out
    assert "repurchase=42" in captured.out
    assert "holdertrade=42" in captured.out


def test_purge_index_dry_run_counts_without_delete():
    from modules.db_admin import purge_index, _INDEX_PURGE_TABLES

    def fake_query(sql, params=None):
        return [{"n": 3}]

    with patch("modules.db_admin.query", side_effect=fake_query) as mock_q, \
         patch("modules.db_admin.execute") as mock_ex:
        counts = purge_index("CSI800", dry_run=True)

    assert mock_ex.call_count == 0
    assert mock_q.call_count == len(_INDEX_PURGE_TABLES)
    assert all(v == 3 for v in counts.values())
    assert set(counts) == set(_INDEX_PURGE_TABLES)


def test_purge_index_deletes_all_index_tables():
    from modules.db_admin import purge_index, _INDEX_PURGE_TABLES

    with patch("modules.db_admin.execute", return_value=2) as mock_ex:
        deleted = purge_index("CSI800", dry_run=False)

    assert mock_ex.call_count == len(_INDEX_PURGE_TABLES)
    assert all(v == 2 for v in deleted.values())
    for call, table in zip(mock_ex.call_args_list, _INDEX_PURGE_TABLES):
        sql, params = call[0][0], call[0][1]
        assert f"DELETE FROM {table}" in sql
        assert params == ("CSI800",)


def test_purge_index_rejects_empty_id():
    from modules.db_admin import purge_index
    import pytest
    with pytest.raises(ValueError):
        purge_index("  ", dry_run=True)
