"""A 股股东回报（分红送股/股票回购/股东增减持）回填，tushare dividend/repurchase/stk_holdertrade 接口。"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

import pymysql.cursors
from tqdm import tqdm

from config import TUSHARE_BACKFILL_START
from core.db_client import get_conn
from ts_ingest.client import get_client
from ts_ingest.transform_shareholder_return import (
    transform_dividend_rows,
    transform_repurchase_rows,
    transform_holdertrade_rows,
)

log = logging.getLogger(__name__)


def _list_a_share_tickers() -> list[str]:
    with get_conn() as conn:
        with conn.cursor(pymysql.cursors.DictCursor) as cur:
            cur.execute(
                "SELECT ticker FROM stocks "
                "WHERE ticker LIKE '%%.SH' OR ticker LIKE '%%.SZ' OR ticker LIKE '%%.BJ' "
                "ORDER BY ticker"
            )
            return [r["ticker"] for r in cur.fetchall()]


def backfill_dividend_one(ts_code: str) -> int:
    client = get_client()
    df = client.call("dividend", ts_code=ts_code)
    if df is None or df.empty:
        return 0
    rows = transform_dividend_rows(df)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO cn_dividend "
                "(ts_code, end_date, ann_date, div_proc, stk_div, stk_bo_rate, stk_co_rate, "
                " cash_div, cash_div_tax, record_date, ex_date, pay_date, div_listdate, "
                " imp_ann_date, base_date, base_share) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                "ON DUPLICATE KEY UPDATE "
                "  div_proc=VALUES(div_proc), stk_div=VALUES(stk_div), "
                "  stk_bo_rate=VALUES(stk_bo_rate), stk_co_rate=VALUES(stk_co_rate), "
                "  cash_div=VALUES(cash_div), cash_div_tax=VALUES(cash_div_tax), "
                "  record_date=VALUES(record_date), ex_date=VALUES(ex_date), "
                "  pay_date=VALUES(pay_date), div_listdate=VALUES(div_listdate), "
                "  imp_ann_date=VALUES(imp_ann_date), base_date=VALUES(base_date), "
                "  base_share=VALUES(base_share)",
                rows,
            )
        conn.commit()
    log.debug(f"dividend@{ts_code}: {len(rows)} rows")
    return len(rows)


def backfill_dividend() -> dict:
    tickers = _list_a_share_tickers()
    total = 0
    for t in tqdm(tickers, desc="dividend", unit="ticker"):
        try:
            total += backfill_dividend_one(t)
        except Exception as e:
            log.error(f"dividend@{t}: {e}")
    log.info(f"dividend: {len(tickers)} tickers, {total} rows")
    return {"rows": total, "tickers": len(tickers)}


def _date_windows(start_yyyymmdd: str, end_yyyymmdd: str, window_days: int) -> list[tuple[str, str]]:
    """[start, end] 切成 window_days 天的窗口列表（闭区间，YYYYMMDD 字符串）。"""
    start = datetime.strptime(start_yyyymmdd, "%Y%m%d")
    end = datetime.strptime(end_yyyymmdd, "%Y%m%d")
    windows = []
    cur = start
    while cur <= end:
        win_end = min(cur + timedelta(days=window_days - 1), end)
        windows.append((cur.strftime("%Y%m%d"), win_end.strftime("%Y%m%d")))
        cur = win_end + timedelta(days=1)
    return windows


def _last_synced_ann_date(table: str) -> str | None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT MAX(ann_date) FROM {table}")
            row = cur.fetchone()
    if row is None or row[0] is None:
        return None
    return row[0].strftime("%Y%m%d")


def backfill_repurchase_window(start_date: str, end_date: str) -> int:
    client = get_client()
    df = client.call("repurchase", start_date=start_date, end_date=end_date)
    if df is None or df.empty:
        return 0
    rows = transform_repurchase_rows(df)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO cn_repurchase "
                "(ts_code, ann_date, end_date, proc, exp_date, vol, amount, high_limit, low_limit) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                "ON DUPLICATE KEY UPDATE "
                "  proc=VALUES(proc), exp_date=VALUES(exp_date), vol=VALUES(vol), "
                "  amount=VALUES(amount), high_limit=VALUES(high_limit), low_limit=VALUES(low_limit)",
                rows,
            )
        conn.commit()
    log.info(f"repurchase@{start_date}-{end_date}: {len(rows)} rows")
    return len(rows)


def backfill_repurchase(start: str | None = None) -> dict:
    if start is None:
        last = _last_synced_ann_date("cn_repurchase")
        if last is None:
            start = TUSHARE_BACKFILL_START
        else:
            start = (datetime.strptime(last, "%Y%m%d") + timedelta(days=1)).strftime("%Y%m%d")
    end = date.today().strftime("%Y%m%d")
    windows = _date_windows(start, end, window_days=365) if start <= end else []
    total = 0
    for s, e in windows:
        try:
            total += backfill_repurchase_window(s, e)
        except Exception as ex:
            log.error(f"repurchase@{s}-{e}: {ex}")
    log.info(f"repurchase: {len(windows)} windows, {total} rows")
    return {"rows": total, "windows": len(windows)}


def backfill_holdertrade_window(start_date: str, end_date: str) -> int:
    client = get_client()
    df = client.call("stk_holdertrade", start_date=start_date, end_date=end_date)
    if df is None or df.empty:
        return 0
    rows = transform_holdertrade_rows(df)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO cn_holdertrade "
                "(ts_code, ann_date, holder_name, holder_type, in_de, change_vol, change_ratio, "
                " after_share, after_ratio, avg_price, total_share, begin_date, close_date) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                "ON DUPLICATE KEY UPDATE "
                "  holder_type=VALUES(holder_type), change_vol=VALUES(change_vol), "
                "  change_ratio=VALUES(change_ratio), after_share=VALUES(after_share), "
                "  after_ratio=VALUES(after_ratio), avg_price=VALUES(avg_price), "
                "  total_share=VALUES(total_share), begin_date=VALUES(begin_date), "
                "  close_date=VALUES(close_date)",
                rows,
            )
        conn.commit()
    log.info(f"stk_holdertrade@{start_date}-{end_date}: {len(rows)} rows")
    return len(rows)


def backfill_holdertrade(start: str | None = None) -> dict:
    if start is None:
        last = _last_synced_ann_date("cn_holdertrade")
        if last is None:
            start = TUSHARE_BACKFILL_START
        else:
            start = (datetime.strptime(last, "%Y%m%d") + timedelta(days=1)).strftime("%Y%m%d")
    end = date.today().strftime("%Y%m%d")
    windows = _date_windows(start, end, window_days=90) if start <= end else []
    total = 0
    for s, e in windows:
        try:
            total += backfill_holdertrade_window(s, e)
        except Exception as ex:
            log.error(f"stk_holdertrade@{s}-{e}: {ex}")
    log.info(f"stk_holdertrade: {len(windows)} windows, {total} rows")
    return {"rows": total, "windows": len(windows)}


def backfill_all(start: str | None = None) -> dict:
    return {
        "dividend": backfill_dividend(),
        "repurchase": backfill_repurchase(start=start),
        "holdertrade": backfill_holdertrade(start=start),
    }
