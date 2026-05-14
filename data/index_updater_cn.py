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
from typing import Optional, Set, Tuple

import pandas as pd

from db import get_conn, query
from ts_ingest.client import get_client
from ts_ingest.ticker_map import index_id_to_ts_code

log = logging.getLogger(__name__)

INDEX_ID = "CSI800"


def update_csi800() -> None:
    conn = get_conn()
    try:
        prev_date = _get_last_snapshot_date(conn, INDEX_ID)
        if prev_date == date.today():
            log.info(f"[{INDEX_ID}] 今日已更新，跳过")
            return

        df = _fetch_csi800()
        if df is None or df.empty:
            log.error(f"[{INDEX_ID}] 获取数据失败")
            _upsert_index_log(conn, INDEX_ID, date.today(), 0, 0, 0, "error", "无数据")
            return

        snap = date.today()
        new_set = set(df["ticker"].unique())
        inserted = _save_snapshot(conn, df, INDEX_ID, snap)
        added, removed = _detect_changes(conn, INDEX_ID, snap, new_set, prev_date)
        _register_stocks(conn, df)
        _upsert_index_log(conn, INDEX_ID, snap, inserted, added, removed)
        log.info(f"[{INDEX_ID}] 完成 {snap}: {inserted}条 +{added} -{removed}")
    except Exception as e:
        log.error(f"[{INDEX_ID}] 更新失败: {e}")
        _upsert_index_log(conn, INDEX_ID, date.today(), 0, 0, 0, "error", str(e))
    finally:
        conn.close()


def _fetch_csi800() -> pd.DataFrame:
    """Fetch CSI800 constituents from tushare index_weight API.

    Returns DataFrame with columns: ticker, name, sector.
    Name and sector are looked up from stocks table (filled by tushare stock_basic).
    """
    client = get_client()
    ts_code = index_id_to_ts_code(INDEX_ID)  # '000906.SH'

    raw = client.call("index_weight", index_code=ts_code)
    if raw.empty:
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


def _get_last_snapshot_date(conn, index_id: str) -> Optional[date]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT MAX(snapshot_date) FROM index_constituents WHERE index_id=%s",
            (index_id,)
        )
        row = cur.fetchone()
    return row[0] if row and row[0] else None


def _save_snapshot(conn, df: pd.DataFrame, index_id: str, snap: date) -> int:
    rows = [
        (index_id, snap, r["ticker"], r["name"], r["sector"])
        for _, r in df.iterrows()
    ]
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT IGNORE INTO index_constituents "
            "(index_id, snapshot_date, ticker, name, sector) VALUES (%s,%s,%s,%s,%s)",
            rows
        )
    conn.commit()
    return len(rows)


def _detect_changes(conn, index_id: str, snap: date,
                    new_set: Set[str], prev_date: Optional[date]) -> Tuple[int, int]:
    if prev_date is None:
        # First-ever snapshot: write all as ADDED
        rows = [(index_id, t, "", "ADDED", snap, None) for t in new_set]
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT IGNORE INTO constituent_changes "
                "(index_id, ticker, name, change_type, change_date, prev_date) "
                "VALUES (%s,%s,%s,%s,%s,%s)",
                rows
            )
        conn.commit()
        return len(rows), 0

    with conn.cursor() as cur:
        cur.execute(
            "SELECT ticker FROM index_constituents WHERE index_id=%s AND snapshot_date=%s",
            (index_id, prev_date)
        )
        prev_set = {r[0] for r in cur.fetchall()}

    added_tickers = new_set - prev_set
    removed_tickers = prev_set - new_set

    rows = []
    for t in added_tickers:
        rows.append((index_id, t, "", "ADDED", snap, prev_date))
    for t in removed_tickers:
        rows.append((index_id, t, "", "REMOVED", snap, prev_date))

    if rows:
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT IGNORE INTO constituent_changes "
                "(index_id, ticker, name, change_type, change_date, prev_date) "
                "VALUES (%s,%s,%s,%s,%s,%s)",
                rows
            )
        conn.commit()
    return len(added_tickers), len(removed_tickers)


def _register_stocks(conn, df: pd.DataFrame) -> None:
    rows = []
    for _, r in df.iterrows():
        ticker = r["ticker"]
        exchange = ticker.split(".")[1]   # SH or SZ
        rows.append((ticker, r["name"], r["sector"], exchange))
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO stocks (ticker, name, gics_sector, exchange) "
            "VALUES (%s,%s,%s,%s) "
            "ON DUPLICATE KEY UPDATE name=VALUES(name), gics_sector=VALUES(gics_sector), "
            "exchange=VALUES(exchange)",
            rows
        )
    conn.commit()


def _upsert_index_log(conn, index_id, snap_date, rows_added, added_count, removed_count,
                      status="ok", message=""):
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO index_sync_log
               (index_id, snapshot_date, rows_added, added_count, removed_count, status, message)
               VALUES (%s,%s,%s,%s,%s,%s,%s)
               ON DUPLICATE KEY UPDATE
                 snapshot_date = VALUES(snapshot_date),
                 rows_added    = VALUES(rows_added),
                 added_count   = VALUES(added_count),
                 removed_count = VALUES(removed_count),
                 last_run      = CURRENT_TIMESTAMP,
                 status        = VALUES(status),
                 message       = VALUES(message)
            """,
            (index_id, snap_date, rows_added, added_count, removed_count, status, message)
        )
    conn.commit()
