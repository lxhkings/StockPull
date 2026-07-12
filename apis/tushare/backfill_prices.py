"""三市场日 K backfill（A/HK 用 qfq 前复权；US 不复权）。"""
from __future__ import annotations

import logging

from tqdm import tqdm

from config import TUSHARE_BACKFILL_START
from core.db_client import get_conn
from modules.sync_log import set_sync_error, set_sync_ok
from apis.tushare.client import get_client
from apis.tushare.transform_prices import pro_bar_rows

log = logging.getLogger(__name__)

SYNC_DATA_TYPE = "price"


def _pro_bar_kwargs(ticker: str, market: str, start: str) -> dict:
    if market == "cn":
        return {"ts_code": ticker, "adj": "qfq", "start_date": start, "freq": "D"}
    if market == "hk":
        return {"ts_code": ticker, "adj": "qfq", "asset": "HK", "start_date": start, "freq": "D"}
    if market == "us":
        return {"ts_code": ticker, "asset": "US", "start_date": start, "freq": "D"}
    raise ValueError(market)


def backfill_one(ticker: str, market: str, start: str = TUSHARE_BACKFILL_START) -> int:
    client = get_client()
    df_raw = client.pro_bar(**_pro_bar_kwargs(ticker, market, start))
    rows = pro_bar_rows(df_raw, ticker)
    if not rows:
        log.warning(f"{ticker}: no bars returned")
        return 0
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO prices (ticker, date, open, high, low, close, volume) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s) "
                "ON DUPLICATE KEY UPDATE "
                "  open=VALUES(open), high=VALUES(high), low=VALUES(low), "
                "  close=VALUES(close), volume=VALUES(volume)",
                rows,
            )
        conn.commit()
        last_date = max(r[1] for r in rows)
        set_sync_ok(conn, ticker, SYNC_DATA_TYPE, last_date, len(rows))
    return len(rows)


def backfill_market(tickers: list[str], market: str,
                    start: str = TUSHARE_BACKFILL_START) -> dict:
    """全 ticker 顺序 backfill；失败计入 sync_log error 并继续。"""
    ok = 0
    failed: list[str] = []
    pbar = tqdm(tickers, desc=f"[{market}]", unit="ticker")
    for t in pbar:
        try:
            backfill_one(t, market=market, start=start)
            ok += 1
        except Exception as e:
            failed.append(t)
            log.error(f"[{market}] {t} backfill failed: {e}")
            try:
                with get_conn() as conn:
                    set_sync_error(conn, t, SYNC_DATA_TYPE, str(e))
            except Exception:
                pass
        pbar.set_postfix(ok=ok, failed=len(failed))
    return {"ok": ok, "failed": failed, "total": len(tickers)}
