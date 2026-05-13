"""HSI (恒生指数) constituent updater via akshare."""

from __future__ import annotations

import logging
from datetime import date

import akshare as ak
import pandas as pd

from db import get_conn
from data.ticker_utils import from_akshare_hk
from data.index_base import (
    get_last_snapshot_date,
    save_snapshot,
    detect_and_record_changes,
    register_stocks,
    upsert_index_log,
)

log = logging.getLogger(__name__)

INDEX_ID = "HSI"
AK_SYMBOL = "HSI"


def update_hsi() -> None:
    conn = get_conn()
    try:
        prev_date = get_last_snapshot_date(conn, INDEX_ID)
        if prev_date == date.today():
            log.info(f"[{INDEX_ID}] 今日已更新，跳过")
            return

        df = _fetch_hsi()
        if df is None or df.empty:
            log.error(f"[{INDEX_ID}] 获取数据失败")
            upsert_index_log(conn, INDEX_ID, date.today(), 0, 0, 0, "error", "无数据")
            return

        snap = date.today()
        new_set = set(df["ticker"].unique())
        inserted = save_snapshot(conn, df, INDEX_ID, snap)
        added, removed = detect_and_record_changes(conn, INDEX_ID, snap, new_set, prev_date)
        register_stocks(conn, df, exchange="HK")
        upsert_index_log(conn, INDEX_ID, snap, inserted, added, removed)
        log.info(f"[{INDEX_ID}] 完成 {snap}: {inserted}条 +{added} -{removed}")
    except Exception as e:
        log.error(f"[{INDEX_ID}] 更新失败: {e}")
        upsert_index_log(conn, INDEX_ID, date.today(), 0, 0, 0, "error", str(e))
    finally:
        conn.close()


def _fetch_hsi() -> pd.DataFrame:
    raw = ak.index_stock_cons(symbol="HSI")
    df = pd.DataFrame({
        "ticker": [from_akshare_hk(str(c).zfill(5)) for c in raw["品种代码"]],
        "name":   raw["品种名称"],
        "sector": raw.get("行业", ""),
    })
    return df