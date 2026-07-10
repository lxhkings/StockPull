from datetime import date

import pandas as pd

from ts_ingest.transform_periodic import resample_ohlcv, periodic_rows


def test_resample_ohlcv_weekly_aggregates_correctly():
    daily = pd.DataFrame({
        "date":   [date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4), date(2024, 1, 5)],
        "open":   [10.0, 11.0, 12.0, 13.0],
        "high":   [11.0, 12.0, 13.0, 14.0],
        "low":    [9.5, 10.5, 11.5, 12.5],
        "close":  [10.5, 11.5, 12.5, 13.5],
        "volume": [100, 200, 300, 400],
    })
    weekly = resample_ohlcv(daily, "W-FRI")
    assert len(weekly) == 1
    row = weekly.iloc[0]
    assert row["open"] == 10.0
    assert row["high"] == 14.0
    assert row["low"] == 9.5
    assert row["close"] == 13.5
    assert row["volume"] == 1000


def test_resample_ohlcv_handles_empty():
    out = resample_ohlcv(pd.DataFrame(columns=["date","open","high","low","close","volume"]), "W-FRI")
    assert out.empty


def test_periodic_rows_builds_tuples_with_ticker():
    df = pd.DataFrame({
        "date": [date(2024, 1, 5)], "open": [10.0], "high": [11.0],
        "low": [9.5], "close": [10.5], "volume": [100],
    })
    rows = periodic_rows("600519.SH", df)
    assert rows == [("600519.SH", date(2024, 1, 5), 10.0, 11.0, 9.5, 10.5, 100)]


def test_periodic_rows_empty_returns_empty_list():
    assert periodic_rows("600519.SH", pd.DataFrame()) == []
