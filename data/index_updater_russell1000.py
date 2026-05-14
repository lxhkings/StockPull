"""Russell 1000 成分股更新模块。

数据源：iShares Russell 1000 ETF (IWB) holdings CSV
https://www.ishares.com/us/products/239707/ishares-russell-1000-value-etf/
约 1008 支成分股（大盘股指数）
"""

from __future__ import annotations

import logging
import requests
from datetime import date

from db import execute, query

log = logging.getLogger(__name__)

IWB_URL = "https://www.ishares.com/us/products/239707/ishares-russell-1000-etf/1467271812596.ajax?fileType=csv&fileName=IWB_holdings&dataType=fund"
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}


def fetch_russell1000_tickers() -> list[str]:
    """从 iShares CSV 抓取 Russell 1000 成分股 ticker 列表。"""
    resp = requests.get(IWB_URL, headers=HEADERS, timeout=15)
    resp.raise_for_status()

    lines = resp.text.split("\n")
    tickers = []

    # CSV 格式：前9行是元数据，第10行开始是表格
    for line in lines[9:]:
        if line.strip() and '"' in line:
            parts = line.split(",")
            if parts:
                ticker = parts[0].strip().replace('"', '')
                if ticker and len(ticker) <= 5:
                    tickers.append(ticker)

    log.info(f"Russell 1000 ETF: 抓取 {len(tickers)} 支成分股")
    return tickers


def update_russell1000() -> tuple[int, int]:
    """更新 Russell 1000 成分股快照。

    Returns:
        (inserted_rows, constituent_count)
    """
    tickers = fetch_russell1000_tickers()
    if not tickers:
        return 0, 0

    today = date.today()
    index_id = "RUSSELL1000"

    # 确保 indices 表有记录
    execute(
        "INSERT IGNORE INTO indices (index_id, name, etf_ticker, description) "
        "VALUES (%s, %s, %s, %s)",
        (index_id, "Russell 1000", "IWB", "Russell 1000 Large Cap Index"),
    )

    # 插入成分股快照
    rows = [(index_id, today, t, None, None) for t in tickers]
    inserted = execute(
        "INSERT IGNORE INTO index_constituents "
        "(index_id, snapshot_date, ticker, name, sector) "
        "VALUES (%s, %s, %s, %s, %s)",
        rows,
        many=True,
    )

    log.info(f"Russell 1000: {inserted} rows inserted, {len(tickers)} constituents")
    return inserted, len(tickers)


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    update_russell1000()