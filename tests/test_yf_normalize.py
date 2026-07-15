import pandas as pd
from datetime import date

from apis.yfinance.normalize import normalize_daily_frame


def test_normalize_daily_empty():
    out = normalize_daily_frame("AAPL", pd.DataFrame())
    assert list(out.columns) == ["ticker", "date", "open", "high", "low", "close", "volume"]
    assert out.empty


def test_normalize_daily_basic_ohlcv():
    sub = pd.DataFrame(
        {
            "Open": [1.0],
            "High": [2.0],
            "Low": [0.5],
            "Close": [1.5],
            "Volume": [100],
        },
        index=pd.DatetimeIndex([pd.Timestamp("2026-07-10")], name="Date"),
    )
    out = normalize_daily_frame("AAPL", sub)
    assert len(out) == 1
    assert out.iloc[0]["ticker"] == "AAPL"
    assert out.iloc[0]["date"] == date(2026, 7, 10)
    assert float(out.iloc[0]["close"]) == 1.5


def test_normalize_daily_drops_null_close():
    sub = pd.DataFrame({
        "Date": pd.to_datetime(["2026-05-04", "2026-05-11"]),
        "Open": [180.0, 185.0],
        "High": [182.0, 187.0],
        "Low": [178.0, 183.0],
        "Close": [None, 186.0],
        "Volume": [1_000_000, 1_200_000],
    })
    out = normalize_daily_frame("AAPL", sub)
    assert len(out) == 1
    assert out["date"].iloc[0] == date(2026, 5, 11)
