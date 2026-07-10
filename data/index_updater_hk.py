"""HSI (恒生指数) constituent updater via local CSV.

Data source: data/hsi_constituents.csv (manually maintained)
"""

from __future__ import annotations

import logging
from datetime import date
import os

import pandas as pd

from core.db_client import get_conn
from data.index_base import (
    get_last_snapshot_date,
    save_snapshot,
    detect_and_record_changes,
    register_stocks,
    upsert_index_log,
)

log = logging.getLogger(__name__)

INDEX_ID = "HSI"


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
    """Fetch HSI constituents from local CSV."""
    try:
        csv_path = os.path.join(os.path.dirname(__file__), "hsi_constituents.csv")
        raw = pd.read_csv(csv_path)

        # Pad code to 5 digits and add .HK suffix
        codes = raw["Code"].astype(str).str.strip().str.zfill(5)
        tickers = codes + ".HK"

        names = raw["Company"].fillna("").astype(str).str.strip()

        df = pd.DataFrame({
            "ticker": tickers,
            "name": names,
            "sector": "",
        })

        # Remove any invalid rows
        df = df[df["ticker"].str.len() == 8]  # Valid format: XXXXX.HK

        log.info(f"[{INDEX_ID}] CSV 找到 {len(df)} 只成分股")
        return df

    except Exception as e:
        log.error(f"[{INDEX_ID}] CSV parse failed: {e}")
        return None