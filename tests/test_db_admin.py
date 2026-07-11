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
        def execute(self, sql): pass
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
