"""三市场日 K 转换：tushare pro_bar 原始 df → prices 表 row tuple。纯函数，零 I/O。"""
from __future__ import annotations

import pandas as pd

from core.http_utils import to_float, to_int


def _normalize_pro_bar(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    out = pd.DataFrame({
        "date": pd.to_datetime(df["trade_date"], format="%Y%m%d").dt.date,
        "open": df["open"].apply(to_float),
        "high": df["high"].apply(to_float),
        "low":  df["low"].apply(to_float),
        "close": df["close"].apply(to_float),
        "volume": df["vol"].apply(to_int),
    })
    return out.sort_values("date").reset_index(drop=True)


def pro_bar_rows(df_raw: pd.DataFrame, ticker: str) -> list[tuple]:
    """tushare pro_bar 原始 df → (ticker, date, open, high, low, close, volume) row tuple 列表。"""
    df = _normalize_pro_bar(df_raw)
    if df.empty:
        return []
    return [
        (ticker, r["date"], r["open"], r["high"], r["low"], r["close"], r["volume"])
        for _, r in df.iterrows()
    ]
