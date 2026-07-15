# tests/test_stock_updater_us_weekly.py
from datetime import date
from unittest.mock import patch, MagicMock
import pandas as pd


# ── _last_us_weekly_date ──────────────────────────────────────────────────────

def test_last_us_weekly_date_monday_morning_returns_prev_monday():
    """Monday before 5am: previous week's Monday."""
    from datetime import datetime
    with patch("apis.yfinance.prices_us_weekly.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2026, 5, 18, 3, 0)  # Monday 03:00
        from apis.yfinance.prices_us_weekly import _last_us_weekly_date
        result = _last_us_weekly_date()
    assert result == date(2026, 5, 11)  # Monday of previous week
    assert result.weekday() == 0


def test_last_us_weekly_date_friday_returns_prev_monday():
    """Friday (any time): previous week's Monday."""
    from datetime import datetime
    with patch("apis.yfinance.prices_us_weekly.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2026, 5, 22, 20, 0)  # Friday 20:00
        from apis.yfinance.prices_us_weekly import _last_us_weekly_date
        result = _last_us_weekly_date()
    assert result == date(2026, 5, 11)
    assert result.weekday() == 0


def test_last_us_weekly_date_saturday_after_5am_returns_this_monday():
    """Saturday after 5am Beijing: week Mon-Fri just closed, return this week's Monday."""
    from datetime import datetime
    with patch("apis.yfinance.prices_us_weekly.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2026, 5, 23, 6, 0)  # Saturday 06:00
        from apis.yfinance.prices_us_weekly import _last_us_weekly_date
        result = _last_us_weekly_date()
    assert result == date(2026, 5, 18)  # Monday of week that just closed
    assert result.weekday() == 0


def test_last_us_weekly_date_saturday_before_5am_returns_prev_monday():
    """Saturday before 5am Beijing: Friday US not yet closed."""
    from datetime import datetime
    with patch("apis.yfinance.prices_us_weekly.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2026, 5, 23, 4, 0)  # Saturday 04:00
        from apis.yfinance.prices_us_weekly import _last_us_weekly_date
        result = _last_us_weekly_date()
    assert result == date(2026, 5, 11)
    assert result.weekday() == 0


def test_last_us_weekly_date_sunday_returns_this_monday():
    """Sunday: last week's Mon-Fri is complete."""
    from datetime import datetime
    with patch("apis.yfinance.prices_us_weekly.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2026, 5, 24, 12, 0)  # Sunday noon
        from apis.yfinance.prices_us_weekly import _last_us_weekly_date
        result = _last_us_weekly_date()
    assert result == date(2026, 5, 18)
    assert result.weekday() == 0


# ── update_weekly_batch precheck ──────────────────────────────────────────────

def test_update_weekly_batch_empty_returns_empty():
    from apis.yfinance.prices_us_weekly import update_weekly_batch
    assert update_weekly_batch([]) == {}


def test_update_weekly_batch_rate_limit_skips_all():
    from apis.yfinance.prices_us_weekly import update_weekly_batch
    with patch("apis.yfinance.prices_us_weekly._last_us_weekly_date", return_value=date(2026, 5, 11)), \
         patch("apis.yfinance.prices_us_weekly._test_aapl_weekly", return_value=(None, "rate_limit")):
        result = update_weekly_batch(["AAPL", "MSFT"])
    assert result == {"AAPL": "error: rate_limit", "MSFT": "error: rate_limit"}


def test_update_weekly_batch_no_data_skips_all():
    from apis.yfinance.prices_us_weekly import update_weekly_batch
    with patch("apis.yfinance.prices_us_weekly._last_us_weekly_date", return_value=date(2026, 5, 11)), \
         patch("apis.yfinance.prices_us_weekly._test_aapl_weekly", return_value=(None, "no_data")):
        result = update_weekly_batch(["AAPL"])
    assert result == {"AAPL": "error: no_data"}


def test_update_weekly_batch_test_error_skips_all():
    from apis.yfinance.prices_us_weekly import update_weekly_batch
    with patch("apis.yfinance.prices_us_weekly._last_us_weekly_date", return_value=date(2026, 5, 11)), \
         patch("apis.yfinance.prices_us_weekly._test_aapl_weekly", return_value=(None, "error")):
        result = update_weekly_batch(["AAPL"])
    assert result == {"AAPL": "error: test_failed"}


# ── normalize_daily_frame（周线共用）──────────────────────────────────────────

def test_normalize_weekly_frame_empty_returns_empty():
    from apis.yfinance.normalize import normalize_daily_frame
    result = normalize_daily_frame("AAPL", pd.DataFrame())
    assert result.empty
    assert list(result.columns) == ["ticker", "date", "open", "high", "low", "close", "volume"]


def test_normalize_weekly_frame_happy_path():
    from apis.yfinance.normalize import normalize_daily_frame
    sub = pd.DataFrame({
        "Date": pd.to_datetime(["2026-05-04", "2026-05-11"]),
        "Open": [180.0, 185.0],
        "High": [182.0, 187.0],
        "Low": [178.0, 183.0],
        "Close": [181.0, 186.0],
        "Volume": [1_000_000, 1_200_000],
    })
    result = normalize_daily_frame("AAPL", sub)
    assert list(result.columns) == ["ticker", "date", "open", "high", "low", "close", "volume"]
    assert len(result) == 2
    assert result["ticker"].iloc[0] == "AAPL"
    assert result["date"].iloc[0] == date(2026, 5, 4)
    assert result["close"].iloc[1] == 186.0


def test_normalize_weekly_frame_drops_null_close():
    from apis.yfinance.normalize import normalize_daily_frame
    sub = pd.DataFrame({
        "Date": pd.to_datetime(["2026-05-04", "2026-05-11"]),
        "Open": [180.0, 185.0],
        "High": [182.0, 187.0],
        "Low": [178.0, 183.0],
        "Close": [None, 186.0],
        "Volume": [1_000_000, 1_200_000],
    })
    result = normalize_daily_frame("AAPL", sub)
    assert len(result) == 1
    assert result["date"].iloc[0] == date(2026, 5, 11)


# ── _save_weekly_prices ───────────────────────────────────────────────────────

def test_save_weekly_prices_uses_prices_weekly_table():
    from apis.yfinance.prices_us_weekly import _save_weekly_prices
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value.__enter__ = lambda s: mock_cur
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

    df = pd.DataFrame({
        "ticker": ["AAPL", "AAPL"],
        "date": [date(2026, 5, 4), date(2026, 5, 11)],
        "open": [180.0, 185.0],
        "high": [182.0, 187.0],
        "low": [178.0, 183.0],
        "close": [181.0, 186.0],
        "volume": [1_000_000, 1_200_000],
    })
    count = _save_weekly_prices(mock_conn, "AAPL", df)
    assert count == 2
    assert mock_cur.executemany.called
    sql = mock_cur.executemany.call_args[0][0]
    assert "prices_weekly" in sql
    assert "INSERT IGNORE" in sql
