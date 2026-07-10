import pandas as pd

from ts_ingest.transform_valuation import transform_valuation_rows


def test_transform_valuation_rows_converts_date_and_casts_floats():
    df = pd.DataFrame({
        "ts_code": ["600519.SH"], "trade_date": ["20260706"],
        "close": [1524.0], "turnover_rate": [0.31], "volume_ratio": [1.9],
        "pe": [25.6], "pe_ttm": [23.15], "pb": [9.22], "ps": [12.96],
        "ps_ttm": [11.59], "total_mv": [191444544.72], "circ_mv": [191444544.72],
    })
    rows = transform_valuation_rows(df)
    assert len(rows) == 1
    row = rows[0]
    assert row[0] == "600519.SH"
    assert row[1] == "2026-07-06"
    assert row[2] == 1524.0


def test_transform_valuation_rows_handles_nan_fields():
    df = pd.DataFrame({
        "ts_code": ["000001.SZ"], "trade_date": ["20260706"],
        "close": [10.5], "turnover_rate": [float("nan")], "volume_ratio": [None],
        "pe": [None], "pe_ttm": [None], "pb": [None], "ps": [None],
        "ps_ttm": [None], "total_mv": [None], "circ_mv": [None],
    })
    rows = transform_valuation_rows(df)
    row = rows[0]
    assert row[0] == "000001.SZ"
    assert row[3] is None  # turnover_rate
    assert row[4] is None  # volume_ratio
