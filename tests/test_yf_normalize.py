import pandas as pd
from datetime import date

from apis.yfinance.normalize import normalize_daily_frame, normalize_intraday_frame


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


def test_normalize_intraday_frame_basic():
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

    result = normalize_intraday_frame("AAPL", "15m", sub)

    assert list(result.columns) == ["ticker", "interval", "datetime", "open", "high", "low", "close", "volume"]
    assert len(result) == 2
    assert result["ticker"].iloc[0] == "AAPL"
    assert result["interval"].iloc[0] == "15m"
    assert result["datetime"].dtype.kind == "M"  # datetime type (ns or us)
    assert result["datetime"].iloc[0].tzinfo is None
    assert result["close"].iloc[0] == 151.0


def test_normalize_intraday_frame_empty():
    result = normalize_intraday_frame("AAPL", "15m", pd.DataFrame())
    assert result.empty
    assert list(result.columns) == ["ticker", "interval", "datetime", "open", "high", "low", "close", "volume"]
