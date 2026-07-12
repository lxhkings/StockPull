"""Trading-day helpers (Beijing wall clock). Pure functions, no I/O."""
from __future__ import annotations
from datetime import datetime, timedelta, date

def last_us_trading_date(now: datetime | None = None) -> date:
    now = now or datetime.now()
    weekday = now.weekday()
    hour = now.hour
    if weekday == 5 or weekday == 6:
        days_back = weekday - 4 if weekday == 5 else 2
        return (now - timedelta(days=days_back)).date()
    if weekday == 0 and hour < 5:
        return (now - timedelta(days=3)).date()
    if hour < 5:
        return (now - timedelta(days=1)).date()
    return (now - timedelta(days=1)).date()

def last_cn_trading_date(now: datetime | None = None) -> date:
    now = now or datetime.now()
    weekday = now.weekday()
    hour = now.hour
    if weekday == 5:
        return (now - timedelta(days=1)).date()
    if weekday == 6:
        return (now - timedelta(days=2)).date()
    if weekday == 0 and hour < 16:
        return (now - timedelta(days=3)).date()
    if hour >= 16:
        return now.date()
    return (now - timedelta(days=1)).date()
