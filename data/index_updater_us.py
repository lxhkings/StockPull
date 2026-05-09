"""
index_updater.py — SP500 指数成分股更新

数据源：
  SP500 → GitHub datasets (含 CIK，直接可用)

职责：
- 从 GitHub/datahub 获取 SP500 成分股列表
- 保存快照到数据库
- 检测并记录成分股变动
- 更新股票基本信息
"""

import pandas as pd
import logging
from io import StringIO
from datetime import date
from typing import Optional, Set, Tuple

from config import INDEX_DELAY
from db import get_conn
from data.base import fetch_urls_sequentially, format_cik

log = logging.getLogger(__name__)

# SP500 数据源（按优先级排序）
SP500_URLS = [
    "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv",
    "https://datahub.io/core/s-and-p-500-companies/r/constituents.csv",
]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 核心功能
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def update_sp500() -> None:
    """
    更新 SP500 指数成分股快照

    流程：
        1. 从 GitHub/datahub 获取最新成分股列表
        2. 保存快照到 index_constituents 表
        3. 检测成分股变动并记录到 constituent_changes 表
        4. 更新 stocks 表基本信息
        5. 更新 index_sync_log 状态
    """
    index_id = "SP500"
    conn = get_conn()

    try:
        prev_date = _get_last_snapshot_date(conn, index_id)

        if prev_date == date.today():
            log.info(f"[{index_id}] 今日已更新，跳过")
            return

        df = _fetch_sp500_data()

        if df is None or df.empty:
            log.error(f"[{index_id}] 获取数据失败")
            _upsert_index_log(conn, index_id, date.today(), 0, 0, 0, "error", "无数据")
            return

        snap_date = date.today()
        new_tickers = set(df["ticker"].unique())

        inserted = _save_snapshot(conn, df, index_id, snap_date)
        added, removed = _detect_and_record_changes(conn, index_id, snap_date, new_tickers, prev_date)
        _register_stocks(conn, df)
        _upsert_index_log(conn, index_id, snap_date, inserted, added, removed)

        log.info(f"[{index_id}] 完成 {snap_date}: {inserted}条 +{added}加入 -{removed}退出")

    except Exception as e:
        log.error(f"[{index_id}] 更新失败: {e}")
        _upsert_index_log(conn, index_id, date.today(), 0, 0, 0, "error", str(e))
    finally:
        conn.close()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 数据获取
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _fetch_sp500_data() -> Optional[pd.DataFrame]:
    """
    从 GitHub/datahub 获取 SP500 成分股列表

    Returns:
        DataFrame with columns: ticker, name, sector, cik, index_id, snapshot_date
    """
    resp = fetch_urls_sequentially(SP500_URLS, context="SP500")

    if resp is None:
        return None

    df = pd.read_csv(StringIO(resp.text))

    # 标准化列名
    col_map = {
        "Symbol": "ticker",
        "Security": "name",
        "GICS Sector": "sector",
        "CIK": "cik",
        "Date added": "date_added",
    }
    df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})

    # 清洗数据
    df = df[df["ticker"].notna()]
    df["ticker"] = df["ticker"].str.strip().str.upper()

    # 格式化 CIK
    if "cik" in df.columns:
        df["cik"] = df["cik"].apply(format_cik)

    # 添加元数据
    df["index_id"] = "SP500"
    df["snapshot_date"] = date.today()

    log.info(f"[SP500] 获取 {len(df)} 只成分股")

    return df


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 数据库操作
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _get_last_snapshot_date(conn, index_id: str) -> Optional[date]:
    """获取上一次快照日期"""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT MAX(snapshot_date) FROM index_constituents WHERE index_id = %s",
            (index_id,),
        )
        result = cur.fetchone()
        return result[0] if result else None


def _save_snapshot(conn, df: pd.DataFrame, index_id: str, snap_date: date) -> int:
    """保存成分股快照到 index_constituents 表"""
    rows = [
        (
            index_id,
            snap_date,
            r.ticker,
            getattr(r, "name", None),
            getattr(r, "sector", None),
        )
        for r in df.itertuples(index=False)
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


def _detect_and_record_changes(
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
        return 0, 0

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
            [(index_id, t, "ADDED", new_date, prev_date) for t in added]
            + [(index_id, t, "REMOVED", new_date, prev_date) for t in removed]
        )
        with conn.cursor() as cur:
            cur.executemany(
                """
                INSERT IGNORE INTO constituent_changes
                    (index_id, ticker, change_type, change_date, prev_date)
                VALUES (%s, %s, %s, %s, %s)
                """,
                rows,
            )
        conn.commit()

    # 日志
    if added:
        log.info(f"[{index_id}] 新加入 {len(added)} 只: {sorted(added)[:10]}")
    if removed:
        log.info(f"[{index_id}] 退出 {len(removed)} 只: {sorted(removed)[:10]}")

    return len(added), len(removed)


def _register_stocks(conn, df: pd.DataFrame) -> None:
    """将成分股基本信息写入 stocks 表"""
    with conn.cursor() as cur:
        for r in df.itertuples(index=False):
            cik = getattr(r, "cik", None)
            cik = cik if cik and str(cik) not in ("nan", "None") else None

            cur.execute(
                """
                INSERT INTO stocks (ticker, name, cik, gics_sector)
                VALUES (%s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    name = COALESCE(VALUES(name), name),
                    cik = COALESCE(VALUES(cik), cik),
                    gics_sector = COALESCE(VALUES(gics_sector), gics_sector)
                """,
                (r.ticker, getattr(r, "name", None), cik, getattr(r, "sector", None)),
            )
    conn.commit()


def _upsert_index_log(
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