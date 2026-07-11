"""A 股每日估值转换：tushare daily_basic 原始 df → cn_valuation_snapshot 表 row。纯函数，零 I/O。"""
from __future__ import annotations

import pandas as pd

from core.http_utils import to_date

_COLS = [
    "close", "turnover_rate", "volume_ratio", "pe", "pe_ttm",
    "pb", "ps", "ps_ttm", "total_mv", "circ_mv", "dv_ratio",
]


def transform_valuation_rows(df: pd.DataFrame) -> list[tuple]:
    rows = []
    for _, r in df.iterrows():
        vals = [None if pd.isna(r.get(c)) else float(r[c]) for c in _COLS]
        rows.append((r["ts_code"], to_date(r["trade_date"]), *vals))
    return rows
