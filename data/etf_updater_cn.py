"""A-share 行业 ETF 后复权日线采集 via tushare fund_daily × fund_adj。

写入 index_prices 表，index_id 使用 ts_code（如 "512800.SH"）。
"""
from __future__ import annotations

import logging
from typing import Optional

import pandas as pd

from ts_ingest.client import get_client

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