"""Futu 采集节流原语。各函数自开 conn（线程安全，适配并发流）。"""
from __future__ import annotations

import logging
from datetime import date

from db import get_conn, set_sync_ok, set_sync_error

log = logging.getLogger(__name__)


def fresh_tickers(data_type: str, refresh_days: int) -> set[str]:
    """返回 sync_log 中 status='ok' 且 last_run 距今 < refresh_days 的 ticker 集合。"""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT ticker FROM sync_log "
                "WHERE data_type=%s AND status='ok' "
                "AND last_run > (NOW() - INTERVAL %s DAY)",
                (data_type, refresh_days),
            )
            return {r[0] for r in cur.fetchall()}
    finally:
        conn.close()


def mark_ok(ticker: str, data_type: str, rows: int = 0) -> None:
    conn = get_conn()
    try:
        set_sync_ok(conn, ticker, data_type, date.today(), rows)
    finally:
        conn.close()


def mark_skip(ticker: str, data_type: str) -> None:
    """永久不支持的票（富途无此票/接口不支持该类型）标记为已处理(ok,0行)，
    使其进入 fresh 集、后续 run 不再重试该接口。窗口到期自动复检（自愈）。"""
    conn = get_conn()
    try:
        set_sync_ok(conn, ticker, data_type, date.today(), 0)
    finally:
        conn.close()


def mark_error(ticker: str, data_type: str, message: str) -> None:
    conn = get_conn()
    try:
        set_sync_error(conn, ticker, data_type, message)
    finally:
        conn.close()