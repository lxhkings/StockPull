"""財務三表轉換：tushare income_vip/balancesheet_vip/cashflow_vip/fina_indicator_vip 原始 df → fin_* 表 row。纯函数，零 I/O。"""
from __future__ import annotations

import json

import pandas as pd

from core.http_utils import to_date


def transform_financial_rows(df: pd.DataFrame, has_report_type: bool) -> list[tuple]:
    """tushare 财务接口原始 df → executemany 用的 row tuple 列表（raw_payload 为整行 JSON）。"""
    rows = []
    for _, r in df.iterrows():
        payload = {k: (None if pd.isna(v) else (float(v) if isinstance(v, (int, float)) else v))
                   for k, v in r.items()}
        if has_report_type:
            rows.append((
                r["ts_code"], to_date(r.get("end_date")),
                to_date(r.get("ann_date")), to_date(r.get("f_ann_date")),
                str(r.get("report_type") or "1"),
                str(r.get("comp_type") or ""),
                json.dumps(payload, ensure_ascii=False),
            ))
        else:
            rows.append((
                r["ts_code"], to_date(r.get("end_date")),
                to_date(r.get("ann_date")),
                json.dumps(payload, ensure_ascii=False),
            ))
    return rows
