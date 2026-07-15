"""列表/成分数据转换：tushare 原始 df → stocks/etf_basic/hk_connect_universe/index_constituents 表 row。纯函数，零 I/O。"""
from __future__ import annotations

import pandas as pd

from core.http_utils import to_date, or_none


def transform_stocks_a(df: pd.DataFrame) -> pd.DataFrame:
    """stock_basic 原始 df → register_stocks 所需的 ticker/name/sector DataFrame。"""
    return pd.DataFrame({
        "ticker": df["ts_code"],
        "name": df["name"],
        "sector": df["industry"],
    })


def transform_stocks_hk(df: pd.DataFrame) -> list[tuple]:
    return [(r["ts_code"], or_none(r["name"]), None, "HKEX") for _, r in df.iterrows()]


def transform_etf_basic(df: pd.DataFrame) -> list[tuple]:
    return [
        (r["ts_code"], or_none(r.get("name")), or_none(r.get("management")), or_none(r.get("custodian")),
         or_none(r.get("fund_type")), or_none(r.get("market")),
         to_date(r.get("list_date")), to_date(r.get("issue_date")),
         to_date(r.get("delist_date")), or_none(r.get("status")))
        for _, r in df.iterrows()
    ]


def transform_hk_connect(df: pd.DataFrame, hs_type: str) -> list[tuple]:
    return [
        (hs_type, r["ts_code"], or_none(r.get("name")),
         to_date(r.get("in_date")), to_date(r.get("out_date")))
        for _, r in df.iterrows()
    ]


def transform_index_weight(df: pd.DataFrame, index_id: str, trade_date: str) -> list[tuple]:
    snap_date = to_date(trade_date)
    return [(index_id, snap_date, r["con_code"], r.get("con_code"), None)
            for _, r in df.iterrows()]
