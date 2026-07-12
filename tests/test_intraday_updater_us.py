"""Tests for data/intraday_updater_us.py"""

from datetime import date, datetime
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest


# ─── DB migration ────────────────────────────────────────────────────────────

def test_create_prices_intraday_table_executes_ddl():
    with patch("modules.db_admin.execute") as mock_execute:
        from modules.db_admin import create_prices_intraday_table
        create_prices_intraday_table()
        mock_execute.assert_called_once()
        sql = mock_execute.call_args[0][0]
        assert "prices_intraday" in sql
        assert "CREATE TABLE IF NOT EXISTS" in sql
        assert "`interval`" in sql


# ─── Pure functions ───────────────────────────────────────────────────────────

def test_sync_type():
    from apis.yfinance.prices_intraday import _sync_type
    assert _sync_type("15m") == "intraday_15m"
    assert _sync_type("1h") == "intraday_60m"


def test_yf_symbol():
    from apis.yfinance.prices_intraday import _yf_symbol
    assert _yf_symbol("BRK.B") == "BRK-B"
    assert _yf_symbol("AAPL") == "AAPL"


def test_normalize_frame_basic():
    idx = pd.to_datetime([
        "2026-05-15 14:30:00+00:00",
        "2026-05-15 14:45:00+00:00",
    ])
    sub = pd.DataFrame({
        "Open":   [150.0, 151.0],
        "High":   [151.5, 152.0],
        "Low":    [149.5, 150.5],
        "Close":  [151.0, 151.5],
        "Volume": [1000000, 900000],
    }, index=idx)
    sub.index.name = "Datetime"

    from apis.yfinance.prices_intraday import _normalize_frame
    result = _normalize_frame("AAPL", "15m", sub)

    assert list(result.columns) == ["ticker", "interval", "datetime", "open", "high", "low", "close", "volume"]
    assert len(result) == 2
    assert result["ticker"].iloc[0] == "AAPL"
    assert result["interval"].iloc[0] == "15m"
    assert result["datetime"].dtype.kind == "M"  # datetime type (ns or us)
    assert result["datetime"].iloc[0].tzinfo is None
    assert result["close"].iloc[0] == 151.0


def test_normalize_frame_empty():
    from apis.yfinance.prices_intraday import _normalize_frame
    result = _normalize_frame("AAPL", "15m", pd.DataFrame())
    assert result.empty
    assert list(result.columns) == ["ticker", "interval", "datetime", "open", "high", "low", "close", "volume"]


# ─── _save_rows ───────────────────────────────────────────────────────────────

def test_save_rows_executes_insert():
    df = pd.DataFrame({
        "ticker":   ["AAPL", "AAPL"],
        "interval": ["15m", "15m"],
        "datetime": [datetime(2026, 5, 15, 14, 30), datetime(2026, 5, 15, 14, 45)],
        "open":     [150.0, 151.0],
        "high":     [151.5, 152.0],
        "low":      [149.5, 150.5],
        "close":    [151.0, 151.5],
        "volume":   [1000000, 900000],
    })
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__ = lambda s: mock_cursor
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

    from apis.yfinance.prices_intraday import _save_rows
    n = _save_rows(mock_conn, df)

    assert n == 2
    mock_cursor.executemany.assert_called_once()
    sql = mock_cursor.executemany.call_args[0][0]
    assert "INSERT IGNORE INTO prices_intraday" in sql
    assert "`interval`" in sql
    mock_conn.commit.assert_called_once()


# ─── update_intraday ──────────────────────────────────────────────────────────

def _make_yf_multiindex_df(symbol: str) -> pd.DataFrame:
    """构造 yfinance 批量下载返回的 MultiIndex DataFrame。
    group_by='ticker' 时 level 0 = ticker, level 1 = price field。
    """
    idx = pd.to_datetime([
        "2026-05-15 14:30:00+00:00",
        "2026-05-15 14:45:00+00:00",
    ])
    cols = pd.MultiIndex.from_tuples(
        [(symbol, col) for col in ["Open", "High", "Low", "Close", "Volume"]],
        names=["Ticker", "Price"],
    )
    data = {
        (symbol, "Open"):   [150.0, 151.0],
        (symbol, "High"):   [151.5, 152.0],
        (symbol, "Low"):    [149.5, 150.5],
        (symbol, "Close"):  [151.0, 151.5],
        (symbol, "Volume"): [1000000, 900000],
    }
    df = pd.DataFrame(data, index=idx)
    df.columns = cols
    df.index.name = "Datetime"
    return df


@patch("apis.yfinance.prices_intraday.get_conn")
@patch("apis.yfinance.prices_intraday.get_last_sync")
@patch("apis.yfinance.prices_intraday.set_sync_ok")
@patch("apis.yfinance.prices_intraday.set_sync_error")
@patch("apis.yfinance.client.yf.download")
@patch("data.market_us.list_active_tickers")
@patch("apis.yfinance.prices_intraday._test_aapl_intraday")
def test_update_intraday_calls_yf_download(
    mock_test_aapl, mock_list, mock_yf_download, mock_set_error, mock_set_ok, mock_get_last_sync, mock_get_conn
):
    # AAPL 测试返回成功
    mock_test_aapl.return_value = (date(2026, 5, 15), "ok")
    mock_list.return_value = ["AAPL"]
    mock_get_last_sync.return_value = None  # 首次：全量拉取
    mock_get_conn.return_value = MagicMock()
    mock_yf_download.return_value = _make_yf_multiindex_df("AAPL")

    with patch("apis.yfinance.prices_intraday._save_rows", return_value=2):
        from apis.yfinance.prices_intraday import update_intraday
        result = update_intraday("15m")

    assert result["AAPL"] == "ok"
    # AAPL 测试被 mock，不调用 yf.download；只有批量下载调用 1 次
    mock_yf_download.assert_called_once()
    assert mock_yf_download.call_args[1]["interval"] == "15m"


@patch("apis.yfinance.prices_intraday.get_conn")
@patch("apis.yfinance.prices_intraday.get_last_sync")
@patch("apis.yfinance.prices_intraday.set_sync_ok")
@patch("apis.yfinance.prices_intraday.set_sync_error")
@patch("apis.yfinance.client.yf.download")
@patch("data.market_us.list_active_tickers")
@patch("apis.yfinance.prices_intraday._test_aapl_intraday")
def test_update_intraday_full_rebase_ignores_sync_log(
    mock_test_aapl, mock_list, mock_yf_download, mock_set_error, mock_set_ok, mock_get_last_sync, mock_get_conn
):
    """full_rebase=True must not call get_last_sync — all tickers start from floor_date."""
    # AAPL 测试返回成功
    mock_test_aapl.return_value = (date(2026, 5, 15), "ok")
    mock_list.return_value = ["AAPL"]
    mock_get_last_sync.return_value = date.today()  # would be "already up to date" in normal mode
    mock_get_conn.return_value = MagicMock()
    mock_yf_download.return_value = _make_yf_multiindex_df("AAPL")

    with patch("apis.yfinance.prices_intraday._save_rows", return_value=2):
        from apis.yfinance.prices_intraday import update_intraday
        result = update_intraday("1h", full_rebase=True)

    mock_get_last_sync.assert_not_called()
    assert result["AAPL"] == "ok"
    # AAPL 测试被 mock，只有批量下载调用 1 次
    mock_yf_download.assert_called_once()
    assert mock_yf_download.call_args[1]["interval"] == "60m"


@patch("apis.yfinance.prices_intraday.get_conn")
@patch("apis.yfinance.prices_intraday.get_last_sync")
@patch("data.market_us.list_active_tickers")
@patch("apis.yfinance.prices_intraday._test_aapl_intraday")
def test_update_intraday_skips_up_to_date_ticker(mock_test_aapl, mock_list, mock_get_last_sync, mock_get_conn):
    # AAPL 测试返回成功，日期匹配
    mock_test_aapl.return_value = (date(2026, 5, 15), "ok")
    mock_list.return_value = ["AAPL"]
    mock_get_last_sync.return_value = date(2026, 5, 15)  # 已同步到最新
    mock_get_conn.return_value = MagicMock()

    with patch("apis.yfinance.client.yf.download") as mock_dl:
        from apis.yfinance.prices_intraday import update_intraday
        result = update_intraday("15m")

    assert result["AAPL"] == "ok"
    # AAPL 测试被 mock，已同步 ticker 不调用批量下载
    mock_dl.assert_not_called()


@patch("apis.yfinance.prices_intraday.get_conn")
@patch("apis.yfinance.prices_intraday.get_last_sync")
@patch("apis.yfinance.prices_intraday.set_sync_ok")
@patch("apis.yfinance.prices_intraday.set_sync_error")
@patch("apis.yfinance.client.yf.download")
@patch("data.market_us.list_active_tickers")
@patch("apis.yfinance.prices_intraday._test_aapl_intraday")
def test_update_intraday_floor_within_yahoo_window(
    mock_test_aapl, mock_list, mock_yf_download, mock_set_error, mock_set_ok, mock_get_last_sync, mock_get_conn
):
    """floor_date 必须以 today 为基准，否则 latest_date<today 时 start 落在 730 天窗口外被拒。"""
    from datetime import timedelta

    # latest_date 比 today 早，模拟非交易日/未收盘
    latest = date.today() - timedelta(days=3)
    mock_test_aapl.return_value = (latest, "ok")
    mock_list.return_value = ["AAPL"]
    mock_get_conn.return_value = MagicMock()
    mock_yf_download.return_value = _make_yf_multiindex_df("AAPL")

    with patch("apis.yfinance.prices_intraday._save_rows", return_value=2):
        from apis.yfinance.prices_intraday import update_intraday
        update_intraday("1h", full_rebase=True)

    # 1h lookback=730，start 必须 = today-729，而非 latest-729
    expected_start = (date.today() - timedelta(days=729)).strftime("%Y-%m-%d")
    assert mock_yf_download.call_args[1]["start"] == expected_start


def test_update_intraday_rejects_unsupported_interval():
    from apis.yfinance.prices_intraday import update_intraday
    with pytest.raises(ValueError, match="Unsupported interval"):
        update_intraday("3m")


# ─── CLI ──────────────────────────────────────────────────────────────────────

def test_cli_intraday_all():
    with patch("apis.yfinance.prices_intraday.update_intraday") as mock_update:
        mock_update.return_value = {"AAPL": "ok"}
        import main
        ret = main.main(["intraday"])
    assert ret == 0
    assert mock_update.call_count == 2
    intervals_called = [c.args[0] for c in mock_update.call_args_list]
    assert "15m" in intervals_called
    assert "1h" in intervals_called


def test_cli_intraday_single_interval():
    with patch("apis.yfinance.prices_intraday.update_intraday") as mock_update:
        mock_update.return_value = {"AAPL": "ok"}
        import main
        ret = main.main(["intraday", "--interval", "15m"])
    assert ret == 0
    mock_update.assert_called_once_with("15m", full_rebase=False)


def test_cli_intraday_rebase_flag():
    with patch("apis.yfinance.prices_intraday.update_intraday") as mock_update:
        mock_update.return_value = {"AAPL": "ok"}
        import main
        ret = main.main(["intraday", "--interval", "1h", "--rebase"])
    assert ret == 0
    mock_update.assert_called_once_with("1h", full_rebase=True)


def test_cli_intraday_no_rebase_flag_default():
    with patch("apis.yfinance.prices_intraday.update_intraday") as mock_update:
        mock_update.return_value = {"AAPL": "ok"}
        import main
        ret = main.main(["intraday", "--interval", "1h"])
    assert ret == 0
    mock_update.assert_called_once_with("1h", full_rebase=False)
