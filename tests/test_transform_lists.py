import pandas as pd

from apis.tushare.transform_lists import (
    transform_stocks_a, transform_stocks_hk, transform_etf_basic,
    transform_hk_connect, transform_index_weight,
)


def test_transform_stocks_a_maps_ticker_name_sector():
    df = pd.DataFrame({
        "ts_code": ["600519.SH"], "symbol": ["600519"],
        "name": ["贵州茅台"], "industry": ["食品饮料"], "exchange": ["SSE"],
    })
    out = transform_stocks_a(df)
    assert list(out.columns) == ["ticker", "name", "sector"]
    assert out.iloc[0].tolist() == ["600519.SH", "贵州茅台", "食品饮料"]


def test_transform_stocks_hk_builds_rows_with_none_sector():
    df = pd.DataFrame({"ts_code": ["00700.HK"], "name": ["腾讯控股"]})
    rows = transform_stocks_hk(df)
    assert rows == [("00700.HK", "腾讯控股", None, "HKEX")]


def test_transform_etf_basic_converts_dates():
    df = pd.DataFrame({
        "ts_code": ["510300.SH"], "name": ["沪深300ETF"],
        "management": ["华泰柏瑞"], "custodian": ["工商银行"],
        "fund_type": ["股票型"], "market": ["E"],
        "list_date": ["20120528"], "issue_date": ["20120508"],
        "delist_date": [None], "status": ["L"],
    })
    rows = transform_etf_basic(df)
    assert rows[0][6] == "2012-05-28"  # list_date
    assert rows[0][7] == "2012-05-08"  # issue_date
    assert rows[0][8] is None          # delist_date


def test_transform_hk_connect_converts_dates():
    df = pd.DataFrame({
        "ts_code": ["600519.SH"], "name": ["贵州茅台"],
        "in_date": ["20141117"], "out_date": [None],
    })
    rows = transform_hk_connect(df, "SH")
    assert rows == [("SH", "600519.SH", "贵州茅台", "2014-11-17", None)]


def test_transform_index_weight_converts_trade_date_to_snap_date():
    df = pd.DataFrame({"con_code": ["600519.SH", "000001.SZ"]})
    rows = transform_index_weight(df, "CSI800", "20260706")
    assert rows == [
        ("CSI800", "2026-07-06", "600519.SH", "600519.SH", None),
        ("CSI800", "2026-07-06", "000001.SZ", "000001.SZ", None),
    ]
