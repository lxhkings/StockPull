"""HSI (恒生指数) constituent updater via Wikipedia.

Data source: https://en.wikipedia.org/wiki/Hang_Seng_Index
"""

from __future__ import annotations

import logging
from datetime import date
from io import StringIO

import pandas as pd
import requests

from db import get_conn
from data.index_base import (
    get_last_snapshot_date,
    save_snapshot,
    detect_and_record_changes,
    register_stocks,
    upsert_index_log,
)

log = logging.getLogger(__name__)

INDEX_ID = "HSI"
WIKI_URL = "https://en.wikipedia.org/wiki/Hang_Seng_Index"


def update_hsi() -> None:
    conn = get_conn()
    try:
        prev_date = get_last_snapshot_date(conn, INDEX_ID)
        if prev_date == date.today():
            log.info(f"[{INDEX_ID}] 今日已更新，跳过")
            return

        df = _fetch_hsi()
        if df is None or df.empty:
            log.error(f"[{INDEX_ID}] 获取数据失败")
            upsert_index_log(conn, INDEX_ID, date.today(), 0, 0, 0, "error", "无数据")
            return

        snap = date.today()
        new_set = set(df["ticker"].unique())
        inserted = save_snapshot(conn, df, INDEX_ID, snap)
        added, removed = detect_and_record_changes(conn, INDEX_ID, snap, new_set, prev_date)
        register_stocks(conn, df, exchange="HK")
        upsert_index_log(conn, INDEX_ID, snap, inserted, added, removed)
        log.info(f"[{INDEX_ID}] 完成 {snap}: {inserted}条 +{added} -{removed}")
    except Exception as e:
        log.error(f"[{INDEX_ID}] 更新失败: {e}")
        upsert_index_log(conn, INDEX_ID, date.today(), 0, 0, 0, "error", str(e))
    finally:
        conn.close()


def _fetch_hsi() -> pd.DataFrame:
    """Fetch HSI constituents from Wikipedia."""
    try:
        resp = requests.get(WIKI_URL, timeout=30)
        if resp.status_code != 200:
            log.error(f"[{INDEX_ID}] Wikipedia fetch failed: {resp.status_code}")
            return None

        # Parse HTML tables
        dfs = pd.read_html(StringIO(resp.text))

        # Find the components table (contains stock codes)
        for df in dfs:
            # Look for table with stock codes (5-digit or 4-digit format)
            if 'Code' in df.columns or 'Ticker' in df.columns or any(df.columns.str.contains('Code', case=False)):
                # Extract code and name columns
                code_col = df.columns[0]  # Usually first column is code
                name_col = df.columns[1]  # Second column is company name

                # Clean code format (pad to 5 digits)
                codes = df[code_col].astype(str).str.strip()
                codes = codes.str.zfill(5)

                # Add .HK suffix
                tickers = codes + ".HK"

                result = pd.DataFrame({
                    "ticker": tickers,
                    "name": df[name_col].astype(str).str.strip(),
                    "sector": None,  # Wikipedia doesn't provide sector
                })

                log.info(f"[{INDEX_ID}] Wikipedia 找到 {len(result)} 只成分股")
                return result

        log.error(f"[{INDEX_ID}] Wikipedia 未找到成分股表格")
        return None

    except Exception as e:
        log.error(f"[{INDEX_ID}] Wikipedia parse failed: {e}")
        return None