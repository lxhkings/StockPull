import pandas as pd

from ts_ingest.transform_shareholder_return import (
    transform_dividend_rows,
    transform_holdertrade_rows,
    transform_repurchase_rows,
)


def test_transform_dividend_rows_converts_dates_and_floats():
    df = pd.DataFrame({
        "ts_code": ["600519.SH"], "end_date": ["20231231"], "ann_date": ["20240328"],
        "div_proc": ["实施"], "stk_div": [0.0], "stk_bo_rate": [0.0], "stk_co_rate": [0.0],
        "cash_div": [19.29], "cash_div_tax": [21.43], "record_date": ["20240612"],
        "ex_date": ["20240613"], "pay_date": ["20240613"], "div_listdate": [None],
        "imp_ann_date": ["20240608"], "base_date": ["20231231"], "base_share": [1256197.8],
    })
    rows = transform_dividend_rows(df)
    assert len(rows) == 1
    row = rows[0]
    assert row[0] == "600519.SH"
    assert row[1] == "2023-12-31"   # end_date
    assert row[2] == "2024-03-28"   # ann_date
    assert row[3] == "实施"          # div_proc
    assert row[7] == 19.29          # cash_div
    assert row[9] == "2024-06-12"   # record_date
    assert row[12] is None          # div_listdate (None input)


def test_transform_dividend_rows_handles_nan_fields():
    df = pd.DataFrame({
        "ts_code": ["000001.SZ"], "end_date": ["20231231"], "ann_date": ["20240328"],
        "div_proc": [None], "stk_div": [None], "stk_bo_rate": [None], "stk_co_rate": [None],
        "cash_div": [None], "cash_div_tax": [None], "record_date": [None],
        "ex_date": [None], "pay_date": [None], "div_listdate": [None],
        "imp_ann_date": [None], "base_date": [None], "base_share": [None],
    })
    rows = transform_dividend_rows(df)
    row = rows[0]
    assert row[3] is None   # div_proc
    assert row[4] is None   # stk_div
    assert row[9] is None   # record_date


def test_transform_repurchase_rows_converts_dates_and_floats():
    df = pd.DataFrame({
        "ts_code": ["600519.SH"], "ann_date": ["20240115"], "end_date": ["20241231"],
        "proc": ["实施中"], "exp_date": ["20241231"], "vol": [1000000.0],
        "amount": [150000000.0], "high_limit": [1800.0], "low_limit": [1200.0],
    })
    rows = transform_repurchase_rows(df)
    assert len(rows) == 1
    row = rows[0]
    assert row[0] == "600519.SH"
    assert row[1] == "2024-01-15"   # ann_date
    assert row[2] == "2024-12-31"   # end_date
    assert row[3] == "实施中"        # proc
    assert row[5] == 1000000.0      # vol


def test_transform_repurchase_rows_handles_nan_fields():
    df = pd.DataFrame({
        "ts_code": ["000001.SZ"], "ann_date": ["20240115"], "end_date": ["20241231"],
        "proc": [None], "exp_date": [None], "vol": [None],
        "amount": [None], "high_limit": [None], "low_limit": [None],
    })
    rows = transform_repurchase_rows(df)
    row = rows[0]
    assert row[3] is None   # proc
    assert row[5] is None   # vol


def test_transform_holdertrade_rows_converts_dates_and_floats():
    df = pd.DataFrame({
        "ts_code": ["600519.SH"], "ann_date": ["20240115"], "holder_name": ["某某股东"],
        "holder_type": ["G"], "in_de": ["DE"], "change_vol": [-50000.0],
        "change_ratio": [-0.04], "after_share": [1200000.0], "after_ratio": [0.1],
        "avg_price": [1650.5], "total_share": [1200000.0],
        "begin_date": ["20240110"], "close_date": ["20240115"],
    })
    rows = transform_holdertrade_rows(df)
    assert len(rows) == 1
    row = rows[0]
    assert row[0] == "600519.SH"
    assert row[2] == "某某股东"       # holder_name
    assert row[4] == "DE"           # in_de
    assert row[5] == -50000.0       # change_vol
    assert row[11] == "2024-01-10"  # begin_date


def test_transform_holdertrade_rows_handles_nan_fields():
    df = pd.DataFrame({
        "ts_code": ["000001.SZ"], "ann_date": ["20240115"], "holder_name": ["某股东"],
        "holder_type": [None], "in_de": ["IN"], "change_vol": [None],
        "change_ratio": [None], "after_share": [None], "after_ratio": [None],
        "avg_price": [None], "total_share": [None],
        "begin_date": [None], "close_date": [None],
    })
    rows = transform_holdertrade_rows(df)
    row = rows[0]
    assert row[3] is None   # holder_type
    assert row[5] is None   # change_vol
    assert row[11] is None  # begin_date
