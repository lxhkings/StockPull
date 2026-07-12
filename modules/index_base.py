"""Index updater shared helpers.

Used by index_updater_us, index_cn (apis.tushare), index_updater_hk.
"""

from __future__ import annotations

from datetime import date
from typing import Optional, Set, Tuple
import pandas as pd



def get_last_snapshot_date(conn, index_id: str) -> Optional[date]:
    """获取上一次快照日期"""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT MAX(snapshot_date) FROM index_constituents WHERE index_id = %s",
            (index_id,),
        )
        result = cur.fetchone()
        return result[0] if result else None


def save_snapshot(conn, df: pd.DataFrame, index_id: str, snap_date: date) -> int:
    """保存成分股快照到 index_constituents 表"""
    rows = [
        (
            index_id,
            snap_date,
            r["ticker"],
            r.get("name", None),
            r.get("sector", None),
        )
        for _, r in df.iterrows()
    ]

    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT IGNORE INTO index_constituents
                (index_id, snapshot_date, ticker, name, sector)
            VALUES (%s, %s, %s, %s, %s)
            """,
            rows,
        )
        inserted = cur.rowcount

    conn.commit()
    return inserted


def detect_and_record_changes(
    conn,
    index_id: str,
    new_date: date,
    new_tickers: Set[str],
    prev_date: Optional[date],
) -> Tuple[int, int]:
    """
    检测成分股变动并记录到 constituent_changes 表

    Returns:
        (added_count, removed_count)
    """
    if not prev_date:
        # First-ever snapshot: mark all as ADDED
        rows = [(index_id, t, "", "ADDED", new_date, None) for t in new_tickers]
        with conn.cursor() as cur:
            cur.executemany(
                """
                INSERT IGNORE INTO constituent_changes
                    (index_id, ticker, name, change_type, change_date, prev_date)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                rows,
            )
        conn.commit()
        return len(rows), 0

    # 获取上次成分股
    with conn.cursor() as cur:
        cur.execute(
            "SELECT ticker FROM index_constituents "
            "WHERE index_id = %s AND snapshot_date = %s",
            (index_id, prev_date),
        )
        prev_tickers = {r[0] for r in cur.fetchall()}

    if not prev_tickers:
        return 0, 0

    # 计算变动
    added = new_tickers - prev_tickers
    removed = prev_tickers - new_tickers

    # 记录变动
    if added or removed:
        rows = (
            [(index_id, t, "", "ADDED", new_date, prev_date) for t in added]
            + [(index_id, t, "", "REMOVED", new_date, prev_date) for t in removed]
        )
        with conn.cursor() as cur:
            cur.executemany(
                """
                INSERT IGNORE INTO constituent_changes
                    (index_id, ticker, name, change_type, change_date, prev_date)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                rows,
            )
        conn.commit()

    return len(added), len(removed)


def register_stocks(conn, df: pd.DataFrame, exchange: str = None) -> None:
    """将成分股基本信息写入 stocks 表

    Args:
        exchange: US market不传，CN/HK传交易所代码
    """
    def _null(v):
        """pandas iterrows 将 None 转为 float NaN，还原为 SQL NULL。"""
        return None if pd.isna(v) else v

    rows = []
    for _, r in df.iterrows():
        ticker = r["ticker"]
        name = _null(r.get("name", None))
        sector = _null(r.get("sector", None))
        if exchange:
            rows.append((ticker, name, sector, exchange))
        else:
            rows.append((ticker, name, sector))

    with conn.cursor() as cur:
        if exchange:
            cur.executemany(
                """
                INSERT INTO stocks (ticker, name, gics_sector, exchange)
                VALUES (%s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    name = COALESCE(VALUES(name), name),
                    gics_sector = COALESCE(VALUES(gics_sector), gics_sector),
                    exchange = VALUES(exchange)
                """,
                rows,
            )
        else:
            cur.executemany(
                """
                INSERT INTO stocks (ticker, name, gics_sector)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    name = COALESCE(VALUES(name), name),
                    gics_sector = COALESCE(VALUES(gics_sector), gics_sector)
                """,
                rows,
            )
    conn.commit()


def upsert_index_log(
    conn,
    index_id: str,
    snap_date: date,
    rows: int,
    added: int,
    removed: int,
    status: str = "ok",
    msg: str = "",
) -> None:
    """更新 index_sync_log 表"""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO index_sync_log
                (index_id, snapshot_date, rows_added, added_count, removed_count, status, message)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                snapshot_date = VALUES(snapshot_date),
                last_run = CURRENT_TIMESTAMP,
                rows_added = VALUES(rows_added),
                added_count = VALUES(added_count),
                removed_count = VALUES(removed_count),
                status = VALUES(status),
                message = VALUES(message)
            """,
            (index_id, snap_date, rows, added, removed, status, msg),
        )
    conn.commit()