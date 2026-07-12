import pandas as pd

from apis.tushare.transform_prices import _normalize_pro_bar, pro_bar_rows


def _bar_df():
    return pd.DataFrame({
        "ts_code": ["600519.SH", "600519.SH"],
        "trade_date": ["20240102", "20240103"],
        "open": [1700.0, 1710.5],
        "high": [1720.0, 1715.0],
        "low":  [1690.0, 1700.0],
        "close": [1715.0, 1705.5],
        "vol":  [12345.0, 23456.0],
    })


def test_normalize_returns_canonical_columns():
    out = _normalize_pro_bar(_bar_df())
    assert list(out.columns) == ["date", "open", "high", "low", "close", "volume"]
    assert str(out.iloc[0]["date"]) == "2024-01-02"


def test_normalize_handles_empty_df():
    out = _normalize_pro_bar(pd.DataFrame())
    assert out.empty


def test_pro_bar_rows_builds_tuples_with_ticker():
    rows = pro_bar_rows(_bar_df(), "600519.SH")
    assert len(rows) == 2
    assert rows[0][0] == "600519.SH"
    assert str(rows[0][1]) == "2024-01-02"
    assert rows[0][2] == 1700.0


def test_pro_bar_rows_empty_returns_empty_list():
    assert pro_bar_rows(pd.DataFrame(), "600519.SH") == []
