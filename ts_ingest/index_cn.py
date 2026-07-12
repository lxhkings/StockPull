"""CSI800 (中证800) constituent updater via tushare.

Mirrors stock_system/data/index_updater.py:update_sp500() flow:
  1. fetch current constituents
  2. write index_constituents snapshot
  3. detect ADDED/REMOVED vs prev snapshot
  4. upsert stocks rows
  5. write index_sync_log
"""

from __future__ import annotations

import logging
from datetime import date

import pandas as pd

from core.db_client import get_conn, query
from ts_ingest.client import get_client
from ts_ingest.ticker_map import index_id_to_ts_code
from modules.index_base import (
    get_last_snapshot_date,
    save_snapshot,
    detect_and_record_changes,
    register_stocks,
    upsert_index_log,
)

log = logging.getLogger(__name__)

INDEX_ID = "CSI800"


def update_csi800() -> None:
    conn = get_conn()
    try:
        prev_date = get_last_snapshot_date(conn, INDEX_ID)
        if prev_date == date.today():
            log.info(f"[{INDEX_ID}] 今日已更新，跳过")
            return

        df = _fetch_csi800()
        if df is None or df.empty:
            log.error(f"[{INDEX_ID}] 获取数据失败")
            upsert_index_log(conn, INDEX_ID, date.today(), 0, 0, 0, "error", "无数据")
            return

        snap = date.today()
        new_set = set(df["ticker"].unique())
        inserted = save_snapshot(conn, df, INDEX_ID, snap)
        added, removed = detect_and_record_changes(conn, INDEX_ID, snap, new_set, prev_date)

        # CN market 需要传 exchange
        register_stocks(conn, df, exchange=None)

        upsert_index_log(conn, INDEX_ID, snap, inserted, added, removed)
        log.info(f"[{INDEX_ID}] 完成 {snap}: {inserted}条 +{added} -{removed}")
    except Exception as e:
        log.error(f"[{INDEX_ID}] 更新失败: {e}")
        upsert_index_log(conn, INDEX_ID, date.today(), 0, 0, 0, "error", str(e))
    finally:
        conn.close()


def _fetch_csi800() -> pd.DataFrame:
    """Fetch CSI800 constituents from tushare index_weight API.

    Returns DataFrame with columns: ticker, name, sector.
    Name and sector are looked up from stocks table (filled by tushare stock_basic).
    """
    try:
        client = get_client()
        ts_code = index_id_to_ts_code(INDEX_ID)  # '000906.SH'

        raw = client.call("index_weight", index_code=ts_code)
        if raw is None or raw.empty:
            log.warning(f"[{INDEX_ID}] index_weight returned empty data")
            return pd.DataFrame(columns=["ticker", "name", "sector"])

        # Validate required columns
        required_cols = ["trade_date", "con_code"]
        missing = [c for c in required_cols if c not in raw.columns]
        if missing:
            log.error(f"[{INDEX_ID}] index_weight missing columns: {missing}")
            return pd.DataFrame(columns=["ticker", "name", "sector"])

        # Filter to latest trade_date (tushare returns multi-period data)
        latest_date = raw["trade_date"].max()
        latest = raw[raw["trade_date"] == latest_date]

        tickers = latest["con_code"].tolist()

        # Lookup name and sector from stocks table
        placeholders = ",".join(["%s"] * len(tickers))
        rows = query(
            f"SELECT ticker, name, gics_sector FROM stocks WHERE ticker IN ({placeholders})",
            tickers,
        )
        stock_map = {r["ticker"]: (r["name"], r.get("gics_sector")) for r in rows}

        df = pd.DataFrame({
            "ticker": tickers,
            "name":   [stock_map.get(t, (None, None))[0] for t in tickers],
            "sector": [stock_map.get(t, (None, None))[1] for t in tickers],
        })
        return df
    except Exception as e:
        log.error(f"[{INDEX_ID}] index_weight call failed: {e}")
        return pd.DataFrame(columns=["ticker", "name", "sector"])


