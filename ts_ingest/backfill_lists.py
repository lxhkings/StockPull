"""列表/成分回填：股票、ETF、沪深港通、指数成分。"""
from __future__ import annotations

import logging
import pandas as pd

from core.db_client import get_conn
from data.index_base import register_stocks
from ts_ingest.client import get_client
from ts_ingest.ticker_map import index_id_to_ts_code

log = logging.getLogger(__name__)


def _to_str(v) -> str | None:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    return str(v)


def _to_date(v):
    if pd.isna(v) or v in (None, ""):
        return None
    s = str(v)
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}" if len(s) == 8 else s


def backfill_stocks_a() -> int:
    """A 股全量股票列表 → stocks（复用 data/index_base.py:register_stocks，
    COALESCE 保护已有 gics_sector 不被空 industry 覆盖）。"""
    client = get_client()
    total = 0
    with get_conn() as conn:
        for ex in ("SSE", "SZSE"):
            df = client.call("stock_basic", exchange=ex, list_status="L",
                             fields="ts_code,symbol,name,area,industry,exchange,list_date")
            stocks_df = pd.DataFrame({
                "ticker": df["ts_code"],
                "name": df["name"],
                "sector": df["industry"],
            })
            register_stocks(conn, stocks_df, exchange=ex)
            total += len(stocks_df)
    log.info(f"stocks_a: upserted {total} rows")
    return total


def backfill_stocks_hk() -> int:
    client = get_client()
    df = client.call("hk_basic", fields="ts_code,name,fullname,list_status,list_date")
    rows = [(r["ts_code"], r["name"], None, "HKEX") for _, r in df.iterrows()]
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT IGNORE INTO stocks (ticker, name, gics_sector, exchange) "
                "VALUES (%s, %s, %s, %s)",
                rows,
            )
        conn.commit()
    log.info(f"stocks_hk: upserted {len(rows)} rows")
    return len(rows)


def backfill_stocks_us() -> int:
    """美股基础信息回填（已禁用）。

    tushare us_basic 数据质量差：
    - name 全空（6000 条无价值）
    - exchange 存为 'US' 而非真实交易所名
    - 包含大量 SPAC/退市/OTC 无效 ticker

    美股数据策略：
    - SP500 成分股：GitHub CSV（index_updater_us.py）
    - 价格数据：yfinance（stock_updater_us.py）
    - 基础信息：无需 tushare，stocks 表已有 SP500 成分股（exchange=Nasdaq/NYSE）
    """
    log.warning("backfill_stocks_us: 已禁用（tushare us_basic 数据质量差），跳过")
    return 0


def backfill_etf_basic() -> int:
    client = get_client()
    fields = "ts_code,name,management,custodian,fund_type,market,list_date,issue_date,delist_date,status"
    dfs = [client.call("fund_basic", market=m) for m in ("E", "O")]
    df = pd.concat(dfs, ignore_index=True)
    rows = [
        (r["ts_code"], r.get("name"), r.get("management"), r.get("custodian"),
         r.get("fund_type"), r.get("market"),
         _to_date(r.get("list_date")), _to_date(r.get("issue_date")),
         _to_date(r.get("delist_date")), r.get("status"))
        for _, r in df.iterrows()
    ]
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO etf_basic "
                "(ts_code, name, management, custodian, fund_type, market, "
                " list_date, issue_date, delist_date, status) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                "ON DUPLICATE KEY UPDATE name=VALUES(name), status=VALUES(status), "
                "delist_date=VALUES(delist_date)",
                rows,
            )
        conn.commit()
    log.info(f"etf_basic: upserted {len(rows)} rows")
    return len(rows)


def backfill_hk_connect() -> int:
    client = get_client()
    total = 0
    for hs_type in ("SH", "SZ"):
        df = client.call("hs_const", hs_type=hs_type)
        rows = [(hs_type, r["ts_code"], r.get("name"),
                 _to_date(r.get("in_date")), _to_date(r.get("out_date")))
                for _, r in df.iterrows()]
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.executemany(
                    "INSERT INTO hk_connect_universe "
                    "(hs_type, ts_code, name, in_date, out_date) "
                    "VALUES (%s,%s,%s,%s,%s) "
                    "ON DUPLICATE KEY UPDATE name=VALUES(name), out_date=VALUES(out_date)",
                    rows,
                )
            conn.commit()
        total += len(rows)
        log.info(f"hk_connect[{hs_type}]: upserted {len(rows)} rows")
    return total


def backfill_index_weight(index_id: str, trade_date: str) -> int:
    """单期指数成分快照 → index_constituents。"""
    client = get_client()
    ts_code = index_id_to_ts_code(index_id)
    df = client.call("index_weight", index_code=ts_code, trade_date=trade_date)
    snap_date = _to_date(trade_date)
    rows = [(index_id, snap_date, r["con_code"], r.get("con_code"), None)
            for _, r in df.iterrows()]
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT IGNORE INTO index_constituents "
                "(index_id, snapshot_date, ticker, name, sector) "
                "VALUES (%s,%s,%s,%s,%s)",
                rows,
            )
        conn.commit()
    log.info(f"index_weight[{index_id}@{snap_date}]: {len(rows)} rows")
    return len(rows)
