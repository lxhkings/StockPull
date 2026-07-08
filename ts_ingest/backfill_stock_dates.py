"""补充 stocks 表的 list_date/delist_date（全A股 PIT universe 前置数据）。"""
import logging

import pandas as pd

from db import get_conn
from ts_ingest.client import get_client

log = logging.getLogger(__name__)


def _to_date(v) -> str | None:
    if v is None or pd.isna(v):
        return None
    s = str(v)
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}" if len(s) == 8 else s


def _sync_status(list_status: str) -> dict:
    client = get_client()
    df: pd.DataFrame = client.call(
        "stock_basic", exchange="", list_status=list_status,
        fields="ts_code,list_date,delist_date",
    )
    if df is None or df.empty:
        return {"status": list_status, "rows": 0, "matched": 0}

    matched = 0
    with get_conn() as conn:
        with conn.cursor() as cur:
            for _, r in df.iterrows():
                list_date = _to_date(r.get("list_date"))
                delist_date = _to_date(r.get("delist_date"))
                cur.execute(
                    "UPDATE stocks SET list_date=%s, delist_date=%s WHERE ticker=%s",
                    (list_date, delist_date, r["ts_code"]),
                )
                matched += cur.rowcount
        conn.commit()
    log.info(f"stock_basic({list_status}): {len(df)} rows fetched, {matched} matched in stocks")
    return {"status": list_status, "rows": len(df), "matched": matched}


def backfill_stock_dates() -> dict:
    """L（上市中）+ D（已退市）两种状态各拉一次，UPDATE 已有 stocks 行。

    未匹配到 stocks 表现有 ticker 的行不会报错（UPDATE 影响 0 行），
    只是不计入 matched 计数，脚本不中断。
    """
    listed = _sync_status("L")
    delisted = _sync_status("D")
    return {"listed": listed, "delisted": delisted}
