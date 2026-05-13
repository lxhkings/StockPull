"""
db.py — 数据库连接 + sync_log 工具
所有模块从这里获取连接，统一管理
"""

import pymysql
import pymysql.cursors
import logging
from datetime import date
from typing import Optional, List, Dict
from config import DB

log = logging.getLogger(__name__)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 连接
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def get_conn() -> pymysql.Connection:
    """获取数据库连接（设置 +08:00 时区，避免 created_at 偏 8 小时）"""
    conn = pymysql.connect(**DB)
    with conn.cursor() as cur:
        cur.execute("SET time_zone = '+08:00'")
    return conn


def query(sql: str, params=None) -> List[Dict]:
    """
    执行 SELECT 并返回 list[dict]
    避免 pd.read_sql 的 backtick/format 问题
    """
    conn = get_conn()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cur:
            cur.execute(sql, params or ())
            return cur.fetchall()
    finally:
        conn.close()


def execute(sql: str, params=None, many: bool = False) -> int:
    """执行 INSERT/UPDATE/DELETE，返回影响行数"""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            if many:
                cur.executemany(sql, params or [])
            else:
                cur.execute(sql, params or ())
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# sync_log
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def get_last_sync(conn, ticker: str, data_type: str) -> Optional[date]:
    """获取 ticker 最后成功同步日期。若 sync_log 无 ok 记录，fallback 到 prices 表查最新日期。"""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT last_date FROM sync_log "
            "WHERE ticker=%s AND data_type=%s AND status='ok'",
            (ticker, data_type)
        )
        row = cur.fetchone()
        if row:
            return row[0]

        # Fallback: 从 prices 表查该 ticker 最新日期（用于 error 状态 ticker 恢复增量）
        if data_type == "price":
            cur.execute(
                "SELECT MAX(date) FROM prices WHERE ticker=%s",
                (ticker,)
            )
            row = cur.fetchone()
            return row[0] if row and row[0] else None

    return None


def set_sync_ok(conn, ticker: str, data_type: str,
                last_date: date, rows_added: int = 0):
    _upsert_sync_log(conn, ticker, data_type, last_date, rows_added, "ok", "")


def set_sync_error(conn, ticker: str, data_type: str, message: str):
    _upsert_sync_log(conn, ticker, data_type, date.today(), 0, "error", message[:500])


def _upsert_sync_log(conn, ticker, data_type, last_date, rows_added, status, message):
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO sync_log
              (ticker, data_type, last_date, rows_added, status, message)
            VALUES (%s,%s,%s,%s,%s,%s)
            ON DUPLICATE KEY UPDATE
              last_date  = IF(VALUES(status)='ok', VALUES(last_date), last_date),
              rows_added = VALUES(rows_added),
              last_run   = CURRENT_TIMESTAMP,
              status     = VALUES(status),
              message    = VALUES(message)
        """, (ticker, data_type, last_date, rows_added, status, message))
    conn.commit()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 常用查询
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def get_all_stocks(conn) -> list:
    with conn.cursor(pymysql.cursors.DictCursor) as cur:
        cur.execute("""
            SELECT ticker, cik, stooq_ticker FROM stocks
            WHERE cik IS NOT NULL AND cik != ''
            ORDER BY ticker
        """)
        return cur.fetchall()


def get_index_tickers(index_id: str) -> List[str]:
    """获取指数最新成分股列表"""
    rows = query("""
        SELECT DISTINCT ticker FROM index_constituents
        WHERE index_id = %s
        AND snapshot_date = (
            SELECT MAX(snapshot_date) FROM index_constituents WHERE index_id = %s
        )
        ORDER BY ticker
    """, (index_id, index_id))
    return [r["ticker"] for r in rows]


def get_latest_snapshot_tickers(index_id: str) -> list[str]:
    """获取指数最新快照的成分股ticker列表"""
    rows = query("""
        SELECT DISTINCT ticker FROM index_constituents
        WHERE index_id = %s
        AND snapshot_date = (
            SELECT MAX(snapshot_date) FROM index_constituents WHERE index_id = %s
        )
        ORDER BY ticker
    """, (index_id, index_id))
    return [r["ticker"] for r in rows]


def get_tickers_without_prices(conn) -> List[str]:
    """返回在 stocks 表中但 prices 表无任何数据的 ticker 列表"""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT s.ticker FROM stocks s
            WHERE s.stooq_ticker IS NOT NULL
              AND s.stooq_ticker != ''
              AND NOT EXISTS (
                  SELECT 1 FROM prices p WHERE p.ticker = s.ticker LIMIT 1
              )
            ORDER BY s.ticker
        """)
        return [r[0] for r in cur.fetchall()]


def show_status():
    """打印数据库同步状态摘要"""
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM stocks")
        total = cur.fetchone()[0]
        cur.execute("SELECT COUNT(DISTINCT ticker) FROM prices")
        with_prices = cur.fetchone()[0]
        cur.execute("SELECT MAX(date) FROM prices")
        last_price = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM sync_log WHERE status='error'")
        errors = cur.fetchone()[0]
    conn.close()
    print(f"股票总数:     {total}")
    print(f"有行情数据:   {with_prices}")
    print(f"行情最新日期: {last_price}")
    print(f"同步错误数:   {errors}")
