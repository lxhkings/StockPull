"""Russell 1000 成分股更新模块。

数据源：iShares Russell 1000 ETF (IWB) holdings CSV
https://www.ishares.com/us/products/239707/ishares-russell-1000-etf/
约 1008 支成分股（大盘股指数）

CSV 字段：Ticker, Name, Sector, Asset Class, ...
"""

from __future__ import annotations

import logging
import requests
import pandas as pd
from io import StringIO
from datetime import date

from db import execute, query, get_conn
from data.index_base import register_stocks

log = logging.getLogger(__name__)

IWB_URL = "https://www.ishares.com/us/products/239707/ishares-russell-1000-etf/1467271812596.ajax?fileType=csv&fileName=IWB_holdings&dataType=fund"
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}


def fetch_russell1000_data() -> pd.DataFrame:
    """从 iShares CSV 抓取 Russell 1000 成分股数据（含 Name, Sector）。"""
    resp = requests.get(IWB_URL, headers=HEADERS, timeout=15)
    resp.raise_for_status()

    # CSV 前9行是元数据，第10行是表头
    lines = resp.text.split("\n")
    header_line = lines[9]
    data_lines = lines[10:]

    # 构造 CSV 文本
    csv_text = header_line + "\n" + "\n".join(data_lines)
    df = pd.read_csv(StringIO(csv_text))

    # 过滤无效行：空ticker、长度>5（股票ticker≤5）、"-"
    df = df[df["Ticker"].notna() & (df["Ticker"] != "-")]
    df["Ticker"] = df["Ticker"].str.strip().str.upper()
    df = df[df["Ticker"].str.len() > 0]  # 过滤空字符串
    df = df[df["Ticker"].str.len() <= 5]

    # 标准化列名
    df = df.rename(columns={"Ticker": "ticker", "Name": "name", "Sector": "sector"})

    # 统一 sector 命名（与 SP500 GICS 一致）
    sector_map = {
        "Communication": "Communication Services",
        "Cash and/or Derivatives": None,  # 非股票类别，过滤
    }
    df["sector"] = df["sector"].replace(sector_map)
    df = df[df["sector"].notna()]  # 过滤非股票类别

    # 填充 NaN 为 None（MySQL 不支持 NaN）
    df = df.where(pd.notnull(df), None)

    log.info(f"Russell 1000 ETF: 抓取 {len(df)} 支成分股")
    return df[["ticker", "name", "sector"]]


def update_russell1000() -> tuple[int, int]:
    """更新 Russell 1000 成分股快照。

    Returns:
        (inserted_rows, constituent_count)
    """
    df = fetch_russell1000_data()
    if df.empty:
        return 0, 0

    today = date.today()
    index_id = "RUSSELL1000"

    conn = get_conn()
    try:
        # 确保 indices 表有记录
        with conn.cursor() as cur:
            cur.execute(
                "INSERT IGNORE INTO indices (index_id, name, etf_ticker, description) "
                "VALUES (%s, %s, %s, %s)",
                (index_id, "Russell 1000", "IWB", "Russell 1000 Large Cap Index"),
            )

        # 插入成分股快照（含 name, sector）
        rows = [(index_id, today, r["ticker"], r["name"], r["sector"]) for _, r in df.iterrows()]
        with conn.cursor() as cur:
            inserted = cur.executemany(
                "INSERT IGNORE INTO index_constituents "
                "(index_id, snapshot_date, ticker, name, sector) "
                "VALUES (%s, %s, %s, %s, %s)",
                rows,
            )

        # 更新 stocks 表（含 name, gics_sector）
        register_stocks(conn, df)

        conn.commit()
        log.info(f"Russell 1000: {inserted} rows inserted, {len(df)} constituents")
        return inserted, len(df)
    finally:
        conn.close()


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    update_russell1000()