from datetime import date
from unittest.mock import patch, MagicMock
import pandas as pd

from ts_ingest.derive_periodic import resample_ohlcv, derive_for_ticker


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


def test_derive_for_ticker_writes_both_tables():
    daily = pd.DataFrame({
        "date":   [date(2024, 1, 2), date(2024, 1, 3)],
        "open":   [10.0, 11.0],
        "high":   [11.0, 12.0],
        "low":    [9.5, 10.5],
        "close":  [10.5, 11.5],
        "volume": [100, 200],
    })
    with patch("ts_ingest.derive_periodic._read_daily", return_value=daily), \
         patch("ts_ingest.derive_periodic.get_conn") as mock_conn:
        cur = MagicMock()
        mock_conn.return_value.__enter__ = lambda s: mock_conn.return_value
        mock_conn.return_value.cursor.return_value.__enter__ = lambda s: cur
        n = derive_for_ticker("600519.SH")
    assert n["weekly"] >= 1
    assert n["monthly"] >= 1
    # 两次 executemany：weekly + monthly
    assert cur.executemany.call_count == 2
