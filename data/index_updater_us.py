"""
index_updater_us.py — SP500 指数成分股更新

数据源：
  SP500 → GitHub datasets (含 CIK，直接可用)
"""

import pandas as pd
import logging
from io import StringIO
from datetime import date

from config import INDEX_DELAY
from core.db_client import get_conn
from core.http_utils import fetch_urls_sequentially, format_cik
from data.index_base import (
    get_last_snapshot_date,
    save_snapshot,
    detect_and_record_changes,
    register_stocks,
    upsert_index_log,
)

log = logging.getLogger(__name__)

# SP500 数据源（按优先级排序）
SP500_URLS = [
    "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv",
    "https://datahub.io/core/s-and-p-500-companies/r/constituents.csv",
]


def update_sp500() -> None:
    """更新 SP500 指数成分股快照"""
    index_id = "SP500"
    conn = get_conn()

    try:
        prev_date = get_last_snapshot_date(conn, index_id)

        if prev_date == date.today():
            log.info(f"[{index_id}] 今日已更新，跳过")
            return

        df = _fetch_sp500_data()

        if df is None or df.empty:
            log.error(f"[{index_id}] 获取数据失败")
            upsert_index_log(conn, index_id, date.today(), 0, 0, 0, "error", "无数据")
            return

        snap_date = date.today()
        new_tickers = set(df["ticker"].unique())

        inserted = save_snapshot(conn, df, index_id, snap_date)
        added, removed = detect_and_record_changes(conn, index_id, snap_date, new_tickers, prev_date)
        register_stocks(conn, df)
        upsert_index_log(conn, index_id, snap_date, inserted, added, removed)

        log.info(f"[{index_id}] 完成 {snap_date}: {inserted}条 +{added}加入 -{removed}退出")

    except Exception as e:
        log.error(f"[{index_id}] 更新失败: {e}")
        upsert_index_log(conn, index_id, date.today(), 0, 0, 0, "error", str(e))
    finally:
        conn.close()


def _fetch_sp500_data() -> pd.DataFrame:
    """从 GitHub/datahub 获取 SP500 成分股列表"""
    resp = fetch_urls_sequentially(SP500_URLS, context="SP500")

    if resp is None:
        return None

    df = pd.read_csv(StringIO(resp.text))

    # 标准化列名
    col_map = {
        "Symbol": "ticker",
        "Security": "name",
        "GICS Sector": "sector",
        "CIK": "cik",
        "Date added": "date_added",
    }
    df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})

    # 清洗数据
    df = df[df["ticker"].notna()]
    df["ticker"] = df["ticker"].str.strip().str.upper()

    # 格式化 CIK
    if "cik" in df.columns:
        df["cik"] = df["cik"].apply(format_cik)

    # 添加元数据
    df["index_id"] = "SP500"
    df["snapshot_date"] = date.today()

    log.info(f"[SP500] 获取 {len(df)} 只成分股")

    return df