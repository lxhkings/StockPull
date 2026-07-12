"""core.trading_calendar pure function tests."""
from datetime import datetime, date

from core.trading_calendar import last_us_trading_date, last_cn_trading_date


# ── US ────────────────────────────────────────────────────────────

def test_last_us_trading_date_saturday_returns_friday():
    # 2026-07-11 is Saturday
    assert last_us_trading_date(datetime(2026, 7, 11, 12, 0)) == date(2026, 7, 10)


def test_last_us_trading_date_monday_before_5am_returns_friday():
    # 2026-07-13 is Monday
    assert last_us_trading_date(datetime(2026, 7, 13, 4, 0)) == date(2026, 7, 10)


def test_last_us_trading_date_sunday_returns_friday():
    # 2026-07-12 is Sunday
    assert last_us_trading_date(datetime(2026, 7, 12, 12, 0)) == date(2026, 7, 10)


def test_last_us_trading_date_weekday_after_5am_returns_prev_day():
    # 2026-07-14 is Tuesday
    assert last_us_trading_date(datetime(2026, 7, 14, 10, 0)) == date(2026, 7, 13)


# ── CN ────────────────────────────────────────────────────────────

def test_last_cn_trading_date_weekday_before_16_returns_prev_day():
    # 2026-07-14 is Tuesday, before 16:00
    assert last_cn_trading_date(datetime(2026, 7, 14, 15, 0)) == date(2026, 7, 13)


def test_last_cn_trading_date_weekday_after_16_returns_today():
    # 2026-07-14 is Tuesday, after 16:00
    assert last_cn_trading_date(datetime(2026, 7, 14, 16, 0)) == date(2026, 7, 14)


def test_last_cn_trading_date_saturday_returns_friday():
    # 2026-07-11 is Saturday
    assert last_cn_trading_date(datetime(2026, 7, 11, 12, 0)) == date(2026, 7, 10)


def test_last_cn_trading_date_monday_before_16_returns_friday():
    # 2026-07-13 is Monday
    assert last_cn_trading_date(datetime(2026, 7, 13, 10, 0)) == date(2026, 7, 10)
