"""A 股股东回报（分红送股/股票回购/股东增减持）转换：tushare dividend/repurchase/stk_holdertrade 原始 df → cn_* 表 row。纯函数，零 I/O。"""
from __future__ import annotations

import pandas as pd

from core.http_utils import to_date, to_float


def _to_str(value) -> str | None:
    return None if pd.isna(value) else str(value)


def transform_dividend_rows(df: pd.DataFrame) -> list[tuple]:
    rows = []
    for _, r in df.iterrows():
        if pd.isna(r.get("ann_date")):
            continue
        rows.append((
            r["ts_code"],
            to_date(r.get("end_date")),
            to_date(r.get("ann_date")),
            _to_str(r.get("div_proc")),
            to_float(r.get("stk_div")),
            to_float(r.get("stk_bo_rate")),
            to_float(r.get("stk_co_rate")),
            to_float(r.get("cash_div")),
            to_float(r.get("cash_div_tax")),
            to_date(r.get("record_date")),
            to_date(r.get("ex_date")),
            to_date(r.get("pay_date")),
            to_date(r.get("div_listdate")),
            to_date(r.get("imp_ann_date")),
            to_date(r.get("base_date")),
            to_float(r.get("base_share")),
        ))
    return rows


def transform_repurchase_rows(df: pd.DataFrame) -> list[tuple]:
    rows = []
    for _, r in df.iterrows():
        rows.append((
            r["ts_code"],
            to_date(r.get("ann_date")),
            to_date(r.get("end_date")) or "9999-12-31",  # null end_date = open-ended buyback, no fixed deadline; sentinel keeps PK/data intact
            _to_str(r.get("proc")),
            to_date(r.get("exp_date")),
            to_float(r.get("vol")),
            to_float(r.get("amount")),
            to_float(r.get("high_limit")),
            to_float(r.get("low_limit")),
        ))
    return rows


def transform_holdertrade_rows(df: pd.DataFrame) -> list[tuple]:
    rows = []
    for _, r in df.iterrows():
        rows.append((
            r["ts_code"],
            to_date(r.get("ann_date")),
            _to_str(r.get("holder_name")),
            _to_str(r.get("holder_type")),
            _to_str(r.get("in_de")),
            to_float(r.get("change_vol")),
            to_float(r.get("change_ratio")),
            to_float(r.get("after_share")),
            to_float(r.get("after_ratio")),
            to_float(r.get("avg_price")),
            to_float(r.get("total_share")),
            to_date(r.get("begin_date")),
            to_date(r.get("close_date")),
        ))
    return rows
