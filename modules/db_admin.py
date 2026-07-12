"""
db_admin.py — 数据库管理查询（跨家族业务模块）

提供指数成分股查询、状态摘要、DDL 等管理功能。
P0.S0.2: get_index_tickers 与 get_latest_snapshot_tickers 实现相同，
后者已删除，统一使用 get_index_tickers。
"""

import logging
from typing import List

import pymysql.cursors

from core.db_client import get_conn, query, execute

log = logging.getLogger(__name__)


def get_all_stocks(conn) -> list:
    """未找到调用者，疑似死代码。返回有 CIK 的 stocks 列表。"""
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


def get_tickers_without_prices(conn) -> List[str]:
    """未找到调用者，疑似死代码。返回在 stocks 表中但 prices 表无数据的 ticker 列表。"""
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


def create_prices_intraday_table() -> None:
    """Create prices_intraday table if not exists. Idempotent."""
    execute("""
        CREATE TABLE IF NOT EXISTS prices_intraday (
            ticker    VARCHAR(20)   NOT NULL,
            `interval` VARCHAR(4)  NOT NULL,
            datetime  DATETIME      NOT NULL,
            open      DECIMAL(12,4),
            high      DECIMAL(12,4),
            low       DECIMAL(12,4),
            close     DECIMAL(12,4),
            volume    BIGINT,
            PRIMARY KEY (ticker, `interval`, datetime),
            INDEX idx_interval_ticker (`interval`, ticker, datetime)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


# 指数维度相关表（有数据的才删；顺序：子表 → indices 元数据）
_INDEX_PURGE_TABLES = (
    "index_prices",
    "index_constituents",
    "constituent_changes",
    "index_sync_log",
    "indices",
)


def count_index_rows(index_id: str) -> dict[str, int]:
    """统计某 index_id 在各指数相关表中的行数。"""
    out: dict[str, int] = {}
    for table in _INDEX_PURGE_TABLES:
        rows = query(
            f"SELECT COUNT(*) AS n FROM {table} WHERE index_id=%s",
            (index_id,),
        )
        out[table] = int(rows[0]["n"]) if rows else 0
    return out


def purge_index(index_id: str, *, dry_run: bool = True) -> dict[str, int]:
    """按 index_id 清理指数相关行。

    dry_run=True（默认）：只返回各表行数，不写库。
    dry_run=False：DELETE 并返回各表删除行数。
    幂等：无数据时返回全 0。
    """
    if not index_id or not str(index_id).strip():
        raise ValueError("index_id is required")
    index_id = str(index_id).strip()

    if dry_run:
        return count_index_rows(index_id)

    deleted: dict[str, int] = {}
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            for table in _INDEX_PURGE_TABLES:
                cur.execute(
                    f"DELETE FROM {table} WHERE index_id=%s",
                    (index_id,),
                )
                deleted[table] = int(cur.rowcount or 0)
        conn.commit()
        return deleted
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


_FUNDAMENTAL_TABLES = (
    "fin_income", "fin_balancesheet", "fin_cashflow", "fin_indicator",
    "cn_valuation_snapshot", "cn_dividend", "cn_repurchase", "cn_holdertrade",
)


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

        rows = {}
        for t in _FUNDAMENTAL_TABLES:
            cur.execute(
                "SELECT table_rows FROM information_schema.tables "
                "WHERE table_schema = DATABASE() AND table_name = %s",
                (t,),
            )
            r = cur.fetchone()
            rows[t] = r[0] if r and r[0] is not None else 0
    conn.close()
    print(f"股票总数:     {total}")
    print(f"有行情数据:   {with_prices}")
    print(f"行情最新日期: {last_price}")
    print(f"同步错误数:   {errors}")
    print()
    print("基本面数据（约数，information_schema 统计，非精确 COUNT）：")
    print(f"  财务三表+指标: fin_income={rows['fin_income']} "
          f"fin_balancesheet={rows['fin_balancesheet']} "
          f"fin_cashflow={rows['fin_cashflow']} "
          f"fin_indicator={rows['fin_indicator']}")
    print(f"  估值快照: cn_valuation_snapshot={rows['cn_valuation_snapshot']}")
    print(f"  股东回报: dividend={rows['cn_dividend']} "
          f"repurchase={rows['cn_repurchase']} "
          f"holdertrade={rows['cn_holdertrade']}")
