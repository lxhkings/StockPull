"""A 股股东回报（分红送股/股票回购/股东增减持）转换：tushare dividend/repurchase/stk_holdertrade 原始 df → cn_* 表 row。纯函数，零 I/O。"""
from __future__ import annotations

import pandas as pd

from core.http_utils import to_date, to_float


def _to_str(value) -> str | None:
    return None if pd.isna(value) else str(value)


def transform_dividend_rows(df: pd.DataFrame) -> list[tuple]:
    rows = []
    for _, r in df.iterrows():
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
            to_date(r.get("end_date")),
            _to_str(r.get("proc")),
            to_date(r.get("exp_date")),
            to_float(r.get("vol")),
            to_float(r.get("amount")),
            to_float(r.get("high_limit")),
            to_float(r.get("low_limit")),
        ))
    return rows
