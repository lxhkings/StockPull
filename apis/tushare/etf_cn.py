"""A-share 行业 ETF 后复权日线采集 via tushare fund_daily × fund_adj。

写入 index_prices 表，index_id 使用 ts_code（如 "512800.SH"）。
"""
from __future__ import annotations

import logging
from typing import Optional

import pandas as pd

from apis.tushare.client import get_client
from core.db_client import query, execute
from config import CN_SECTOR_ETFS
from core.http_utils import to_float

log = logging.getLogger(__name__)


def fetch_etf_daily_hfq(ts_code: str, start_date: Optional[str]) -> pd.DataFrame:
    """拉取单只 ETF 后复权日线。

    Returns DataFrame[date, hfq_close]，按 date 升序。
    空 fund_daily 返回空 DataFrame。
    空 fund_adj 时 fallback raw close 并 warn。
    """
    client = get_client()

    daily = client.call("fund_daily", ts_code=ts_code, start_date=start_date)
    if daily is None or daily.empty:
        return pd.DataFrame()

    adj = client.call("fund_adj", ts_code=ts_code, start_date=start_date)

    if adj is None or adj.empty:
        log.warning(f"[{ts_code}] fund_adj 空，使用 raw close")
        df = daily[["trade_date", "close"]].copy()
        df["hfq_close"] = df["close"].astype(float)
    else:
        df = daily.merge(
            adj[["trade_date", "adj_factor"]],
            on="trade_date",
            how="left",
        )
        df = df.sort_values("trade_date")
        df["adj_factor"] = df["adj_factor"].ffill().bfill().fillna(1.0)
        df["hfq_close"] = df["close"].astype(float) * df["adj_factor"].astype(float)

    df["date"] = pd.to_datetime(df["trade_date"]).dt.date
    return df[["date", "hfq_close"]].sort_values("date").reset_index(drop=True)


def update_etf_prices(full_rebase: bool = False) -> int:
    """遍历 CN_SECTOR_ETFS，增量或全量写入 index_prices。

    full_rebase=True 时忽略 last_date，从 2010-01-01 全量重灌。
    单只 ETF 失败不阻断其他（log error 跳过）。
    """
    total = 0
    for ts_code, meta in CN_SECTOR_ETFS.items():
        try:
            if full_rebase:
                last_date = None
                start = "20100101"
            else:
                last = query(
                    "SELECT MAX(date) AS d FROM index_prices WHERE index_id=%s",
                    (ts_code,),
                )
                last_date = last[0]["d"] if last and last[0]["d"] else None
                start = last_date.strftime("%Y%m%d") if last_date else "20100101"

            df = fetch_etf_daily_hfq(ts_code, start_date=start)
            if df.empty:
                continue

            if last_date is not None:
                df = df[df["date"] > last_date]
            if df.empty:
                continue

            rows = [
                (r.date, ts_code, to_float(r.hfq_close))
                for r in df.itertuples(index=False)
            ]
            n = execute(
                "INSERT IGNORE INTO index_prices (date, index_id, close) VALUES (%s,%s,%s)",
                rows,
                many=True,
            )
            total += n
            log.info(f"[{ts_code}] {meta['name']} 写入 {n} 行")
        except Exception as e:
            log.error(f"[{ts_code}] 失败: {e}")
            continue
    return total