"""A 股每日估值快照，使用 Tushare daily_basic 全市场单日批量接口。"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

import pymysql.cursors

from config import TUSHARE_BACKFILL_START
from core.db_client import get_conn
from ts_ingest.client import get_client
from ts_ingest.transform_valuation import transform_valuation_rows

log = logging.getLogger(__name__)


def _trading_dates(start_yyyymmdd: str) -> list[str]:
    """从现有 prices 表取 A 股交易日历（YYYYMMDD 字符串，升序）。"""
    start = f"{start_yyyymmdd[:4]}-{start_yyyymmdd[4:6]}-{start_yyyymmdd[6:8]}"
    with get_conn() as conn:
        with conn.cursor(pymysql.cursors.DictCursor) as cur:
            cur.execute(
                "SELECT DISTINCT date FROM prices "
                "WHERE (ticker LIKE '%%.SH' OR ticker LIKE '%%.SZ' OR ticker LIKE '%%.BJ') "
                "  AND date >= %s ORDER BY date",
                (start,),
            )
            return [r["date"].strftime("%Y%m%d") for r in cur.fetchall()]


def backfill_day(trade_date: str) -> int:
    client = get_client()
    df = client.call("daily_basic", trade_date=trade_date)
    if df is None or df.empty:
        return 0
    rows = transform_valuation_rows(df)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO cn_valuation_snapshot "
                "(ts_code, trade_date, close, turnover_rate, volume_ratio, "
                " pe, pe_ttm, pb, ps, ps_ttm, total_mv, circ_mv) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                "ON DUPLICATE KEY UPDATE "
                "  close=VALUES(close), turnover_rate=VALUES(turnover_rate), "
                "  volume_ratio=VALUES(volume_ratio), pe=VALUES(pe), pe_ttm=VALUES(pe_ttm), "
                "  pb=VALUES(pb), ps=VALUES(ps), ps_ttm=VALUES(ps_ttm), "
                "  total_mv=VALUES(total_mv), circ_mv=VALUES(circ_mv)",
                rows,
            )
        conn.commit()
    log.info(f"daily_basic@{trade_date}: {len(rows)} rows")
    return len(rows)


def _last_synced_date() -> str | None:
    """DB 里已有的最新 trade_date（YYYYMMDD）。空表返回 None（首次运行）。"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT MAX(trade_date) FROM cn_valuation_snapshot")
            row = cur.fetchone()
    if row is None or row[0] is None:
        return None
    return row[0].strftime("%Y%m%d")


def backfill_all(start: str | None = None) -> dict:
    """默认增量：从 DB 里已同步的最新交易日之后开始（cron 每日跑安全，
    不会重新拉全部历史）。首次运行（表为空）时全量回填，从
    TUSHARE_BACKFILL_START 开始。显式传 start 可强制指定起点（例如
    补历史缺口或重新全量回填）。
    """
    if start is None:
        last = _last_synced_date()
        if last is None:
            start = TUSHARE_BACKFILL_START
        else:
            next_day = datetime.strptime(last, "%Y%m%d") + timedelta(days=1)
            start = next_day.strftime("%Y%m%d")

    dates = _trading_dates(start)
    log.info(f"valuation backfill: {len(dates)} trading days")
    total = 0
    for d in dates:
        try:
            total += backfill_day(d)
        except Exception as e:
            log.error(f"daily_basic@{d}: {e}")
    return {"rows": total, "days": len(dates)}
