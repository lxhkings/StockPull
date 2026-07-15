"""US index / sector-ETF daily close via yfinance → index_prices.

Symbols: ^GSPC (SP500), ^RUT (RUSSELL1000), QQQ + GICS sector ETFs.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from core.db_client import query, execute
from core.http_utils import to_float
from core.trading_calendar import last_us_trading_date
from apis.yfinance.client import download_with_retry
from apis.yfinance.normalize import lower_ohlc_columns

log = logging.getLogger(__name__)

# (yfinance symbol, index_prices.index_id)
US_INDEX_SYMBOLS: list[tuple[str, str]] = [
    ("^GSPC", "SP500"),
    ("^RUT", "RUSSELL1000"),
    ("QQQ", "QQQ"),
    ("XLK", "XLK"),
    ("XLY", "XLY"),
    ("XLF", "XLF"),
    ("XLV", "XLV"),
    ("XLP", "XLP"),
    ("XLI", "XLI"),
    ("XLE", "XLE"),
    ("XLB", "XLB"),
    ("XLRE", "XLRE"),
    ("XLU", "XLU"),
    ("XLC", "XLC"),
]


def update_index_prices() -> int:
    """增量拉取 US 指数/行业 ETF 日线 close，写入 index_prices。返回写入行数。"""
    last_trading = last_us_trading_date()
    total = 0
    for symbol, index_id in US_INDEX_SYMBOLS:
        last = query(
            "SELECT MAX(date) AS d FROM index_prices WHERE index_id=%s", (index_id,)
        )
        last_date = last[0]["d"] if last and last[0]["d"] else None

        if last_date and last_date >= last_trading:
            continue

        start = last_date.isoformat() if last_date else "2010-01-01"
        end = (last_trading + timedelta(days=1)).isoformat()
        try:
            df = download_with_retry(
                tickers=symbol, start=start, end=end, interval="1d",
                group_by="column", context=f"[{symbol} index price] ",
            )
        except Exception as e:
            log.warning(f"[{symbol}] index price yfinance 失败，跳过: {e}")
            continue
        if df.empty:
            continue

        df = lower_ohlc_columns(df.reset_index())
        rows = []
        for _, r in df.iterrows():
            d = r["date"].date() if hasattr(r["date"], "date") else r["date"]
            if last_date and d <= last_date:
                continue
            rows.append((d, index_id, to_float(r.get("close"))))

        if not rows:
            continue

        total += execute(
            "INSERT IGNORE INTO index_prices (date, index_id, close) VALUES (%s,%s,%s)",
            rows, many=True,
        )
    return total
