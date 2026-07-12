# tests/test_stock_updater_cn_weekly.py
from datetime import date
from unittest.mock import patch, MagicMock
import pandas as pd


# ── _normalize_pro_bar ────────────────────────────────────────────────────────

def test_normalize_pro_bar_happy_path():
    from data.stock_updater_cn_weekly import _normalize_pro_bar
    df = pd.DataFrame({
        "trade_date": ["20260511", "20260518"],
        "open":  [100.0, 102.0],
        "high":  [105.0, 106.0],
        "low":   [99.0,  101.0],
        "close": [103.0, 104.0],
        "vol":   [1_000_000, 1_200_000],
    })
    result = _normalize_pro_bar(df)
    assert list(result.columns) == ["date", "open", "high", "low", "close", "volume"]
    assert len(result) == 2
    assert result["date"].iloc[0] == date(2026, 5, 11)
    assert result["close"].iloc[1] == 104.0


def test_normalize_pro_bar_empty():
    from data.stock_updater_cn_weekly import _normalize_pro_bar
    result = _normalize_pro_bar(pd.DataFrame())
    assert result.empty


def test_normalize_pro_bar_sorted_ascending():
    """Rows returned in ascending date order regardless of tushare order."""
    from data.stock_updater_cn_weekly import _normalize_pro_bar
    df = pd.DataFrame({
        "trade_date": ["20260518", "20260511"],  # reversed
        "open":  [102.0, 100.0],
        "high":  [106.0, 105.0],
        "low":   [101.0, 99.0],
        "close": [104.0, 103.0],
        "vol":   [1_200_000, 1_000_000],
    })
    result = _normalize_pro_bar(df)
    assert result["date"].iloc[0] == date(2026, 5, 11)
    assert result["date"].iloc[1] == date(2026, 5, 18)


# ── _save_weekly_prices_batch ─────────────────────────────────────────────────

def test_save_weekly_prices_batch_uses_prices_weekly_table():
    from data.stock_updater_cn_weekly import _save_weekly_prices_batch
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value.__enter__ = lambda s: mock_cur
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

    rows = [("600519.SH", date(2026, 5, 15), 100.0, 105.0, 99.0, 103.0, 1_000_000)]
    count = _save_weekly_prices_batch(mock_conn, rows)

    assert count == 1
    assert mock_cur.executemany.called
    sql = mock_cur.executemany.call_args[0][0]
    assert "prices_weekly" in sql
    assert "ON DUPLICATE KEY UPDATE" in sql


# ── update_weekly_batch ───────────────────────────────────────────────────────

def test_update_weekly_batch_empty():
    from data.stock_updater_cn_weekly import update_weekly_batch
    assert update_weekly_batch([]) == {}


def test_update_weekly_batch_all_already_synced():
    """All tickers already at last_trading: skips without fetching."""
    from data.stock_updater_cn_weekly import update_weekly_batch
    with patch("data.stock_updater_cn_weekly.last_cn_trading_date",
               return_value=date(2026, 5, 16)), \
         patch("data.stock_updater_cn_weekly.get_conn") as mock_conn_fn, \
         patch("data.stock_updater_cn_weekly.get_last_sync",
               return_value=date(2026, 5, 16)):
        mock_conn = MagicMock()
        mock_conn_fn.return_value = mock_conn
        result = update_weekly_batch(["600519.SH", "000001.SZ"])
    assert result == {}


def test_update_weekly_batch_new_tickers_trigger_full_backfill():
    """New tickers (no sync_log) trigger full history fetch."""
    from data.stock_updater_cn_weekly import update_weekly_batch
    from config import TUSHARE_BACKFILL_START

    with patch("data.stock_updater_cn_weekly.last_cn_trading_date",
               return_value=date(2026, 5, 16)), \
         patch("data.stock_updater_cn_weekly.get_conn") as mock_conn_fn, \
         patch("data.stock_updater_cn_weekly.get_last_sync", return_value=None), \
         patch("data.stock_updater_cn_weekly._fetch_one", return_value=pd.DataFrame({
             "date": [date(2026, 5, 16)],
             "open": [100.0], "high": [105.0], "low": [99.0],
             "close": [103.0], "volume": [1_000_000],
         })) as mock_fetch, \
         patch("data.stock_updater_cn_weekly._flush_batch"):
        mock_conn = MagicMock()
        mock_conn_fn.return_value = mock_conn
        result = update_weekly_batch(["600519.SH"])

    assert mock_fetch.called
    start_arg = mock_fetch.call_args[0][1]
    assert start_arg == TUSHARE_BACKFILL_START


def test_sync_data_type_is_price_weekly():
    """SYNC_DATA_TYPE constant must be 'price_weekly'."""
    from data.stock_updater_cn_weekly import SYNC_DATA_TYPE
    assert SYNC_DATA_TYPE == "price_weekly"
