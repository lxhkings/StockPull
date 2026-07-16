# tests/test_stock_updater_us_weekly.py
from datetime import date
from unittest.mock import patch
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
         patch("apis.yfinance.prices_us_weekly.probe_weekly", return_value="rate_limit"):
        result = update_weekly_batch(["AAPL", "MSFT"])
    assert result == {"AAPL": "error: rate_limit", "MSFT": "error: rate_limit"}


def test_update_weekly_batch_no_data_skips_all():
    from apis.yfinance.prices_us_weekly import update_weekly_batch
    with patch("apis.yfinance.prices_us_weekly._last_us_weekly_date", return_value=date(2026, 5, 11)), \
         patch("apis.yfinance.prices_us_weekly.probe_weekly", return_value="no_data"):
        result = update_weekly_batch(["AAPL"])
    assert result == {"AAPL": "error: no_data"}


def test_update_weekly_batch_test_error_skips_all():
    from apis.yfinance.prices_us_weekly import update_weekly_batch
    with patch("apis.yfinance.prices_us_weekly._last_us_weekly_date", return_value=date(2026, 5, 11)), \
         patch("apis.yfinance.prices_us_weekly.probe_weekly", return_value="error"):
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


# ── weekly batch entry contract ───────────────────────────────────────────────

def test_build_us_weekly_spec_contract():
    """Weekly Spec: table / data_type / interval / on_duplicate / end window."""
    from apis.yfinance.prices_us_weekly import build_us_weekly_spec

    spec = build_us_weekly_spec()
    assert spec.price_table == "prices_weekly"
    assert spec.data_type == "price_weekly"
    assert spec.interval == "1wk"
    assert spec.on_duplicate is False
    assert spec.support_years is False
    assert spec.label == "weekly batch"
    # end window: target + 7 days (Callable until Task 6 end_pad_days)
    from datetime import date as d
    t = d(2026, 5, 11)
    assert spec.end_exclusive(t) == d(2026, 5, 18)
