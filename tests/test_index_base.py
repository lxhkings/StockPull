"""data/index_base.py 成分股快照通用操作测试。"""
from unittest.mock import MagicMock
from datetime import date
import pandas as pd

from data.index_base import (
    get_last_snapshot_date,
    save_snapshot,
    detect_and_record_changes,
    register_stocks,
    upsert_index_log,
)


def _conn_with_cursor():
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cur
    return conn, cur


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# get_last_snapshot_date
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_get_last_snapshot_date_returns_max_date():
    conn, cur = _conn_with_cursor()
    cur.fetchone.return_value = (date(2026, 7, 1),)
    result = get_last_snapshot_date(conn, "CSI800")
    assert result == date(2026, 7, 1)
    cur.execute.assert_called_once()
    args = cur.execute.call_args[0]
    assert "MAX(snapshot_date)" in args[0]
    assert args[1] == ("CSI800",)


def test_get_last_snapshot_date_returns_none_when_no_rows():
    conn, cur = _conn_with_cursor()
    cur.fetchone.return_value = (None,)
    assert get_last_snapshot_date(conn, "CSI800") is None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# save_snapshot
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_save_snapshot_inserts_all_rows():
    conn, cur = _conn_with_cursor()
    cur.rowcount = 2
    df = pd.DataFrame({
        "ticker": ["600519.SH", "000001.SZ"],
        "name": ["贵州茅台", "平安银行"],
        "sector": ["食品饮料", "银行"],
    })
    inserted = save_snapshot(conn, df, "CSI800", date(2026, 7, 1))
    assert inserted == 2
    sql, rows = cur.executemany.call_args[0]
    assert "INSERT IGNORE INTO index_constituents" in sql
    assert rows == [
        ("CSI800", date(2026, 7, 1), "600519.SH", "贵州茅台", "食品饮料"),
        ("CSI800", date(2026, 7, 1), "000001.SZ", "平安银行", "银行"),
    ]
    conn.commit.assert_called_once()


def test_save_snapshot_defaults_missing_name_sector_to_none():
    conn, cur = _conn_with_cursor()
    cur.rowcount = 1
    df = pd.DataFrame({"ticker": ["999999.SH"]})
    save_snapshot(conn, df, "CSI800", date(2026, 7, 1))
    _, rows = cur.executemany.call_args[0]
    assert rows == [("CSI800", date(2026, 7, 1), "999999.SH", None, None)]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# detect_and_record_changes
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_detect_changes_first_snapshot_marks_all_added():
    conn, cur = _conn_with_cursor()
    added, removed = detect_and_record_changes(
        conn, "CSI800", date(2026, 7, 1), {"A", "B"}, prev_date=None,
    )
    assert (added, removed) == (2, 0)
    sql, rows = cur.executemany.call_args[0]
    assert "INSERT IGNORE INTO constituent_changes" in sql
    assert {r[1] for r in rows} == {"A", "B"}
    assert all(r[3] == "ADDED" for r in rows)
    assert all(r[5] is None for r in rows)  # prev_date
    conn.commit.assert_called_once()


def test_detect_changes_no_prev_tickers_returns_zero_without_write():
    conn, cur = _conn_with_cursor()
    cur.fetchall.return_value = []  # 上次快照日期存在但查不到成分股
    added, removed = detect_and_record_changes(
        conn, "CSI800", date(2026, 7, 2), {"A", "B"}, prev_date=date(2026, 7, 1),
    )
    assert (added, removed) == (0, 0)
    cur.executemany.assert_not_called()
    conn.commit.assert_not_called()


def test_detect_changes_computes_added_and_removed():
    conn, cur = _conn_with_cursor()
    cur.fetchall.return_value = [("A",), ("B",)]  # 上次成分股 A, B
    added, removed = detect_and_record_changes(
        conn, "CSI800", date(2026, 7, 2), {"B", "C"}, prev_date=date(2026, 7, 1),
    )
    assert (added, removed) == (1, 1)  # C 新增, A 移除
    sql, rows = cur.executemany.call_args[0]
    added_rows = [r for r in rows if r[3] == "ADDED"]
    removed_rows = [r for r in rows if r[3] == "REMOVED"]
    assert [r[1] for r in added_rows] == ["C"]
    assert [r[1] for r in removed_rows] == ["A"]
    assert all(r[5] == date(2026, 7, 1) for r in rows)  # prev_date 传入变动记录
    conn.commit.assert_called_once()


def test_detect_changes_no_diff_skips_write():
    conn, cur = _conn_with_cursor()
    cur.fetchall.return_value = [("A",), ("B",)]
    added, removed = detect_and_record_changes(
        conn, "CSI800", date(2026, 7, 2), {"A", "B"}, prev_date=date(2026, 7, 1),
    )
    assert (added, removed) == (0, 0)
    cur.executemany.assert_not_called()
    conn.commit.assert_not_called()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# register_stocks
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_register_stocks_without_exchange_uses_3col_sql():
    conn, cur = _conn_with_cursor()
    df = pd.DataFrame({"ticker": ["600519.SH"], "name": ["贵州茅台"], "sector": ["食品饮料"]})
    register_stocks(conn, df)
    sql, rows = cur.executemany.call_args[0]
    assert "gics_sector" in sql
    assert "exchange" not in sql
    assert rows == [("600519.SH", "贵州茅台", "食品饮料")]
    assert "COALESCE(VALUES(name), name)" in sql
    conn.commit.assert_called_once()


def test_register_stocks_with_exchange_uses_4col_sql():
    conn, cur = _conn_with_cursor()
    df = pd.DataFrame({"ticker": ["00700.HK"], "name": ["腾讯控股"], "sector": [None]})
    register_stocks(conn, df, exchange="HK")
    sql, rows = cur.executemany.call_args[0]
    assert "exchange" in sql
    assert rows == [("00700.HK", "腾讯控股", None, "HK")]


def test_register_stocks_converts_nan_to_none():
    conn, cur = _conn_with_cursor()
    df = pd.DataFrame({"ticker": ["XYZ"], "name": [float("nan")], "sector": [float("nan")]})
    register_stocks(conn, df)
    _, rows = cur.executemany.call_args[0]
    assert rows == [("XYZ", None, None)]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# upsert_index_log
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_upsert_index_log_writes_expected_params():
    conn, cur = _conn_with_cursor()
    upsert_index_log(conn, "CSI800", date(2026, 7, 1), 800, 3, 2, status="ok", msg="")
    sql, params = cur.execute.call_args[0]
    assert "INSERT INTO index_sync_log" in sql
    assert "ON DUPLICATE KEY UPDATE" in sql
    assert params == ("CSI800", date(2026, 7, 1), 800, 3, 2, "ok", "")
    conn.commit.assert_called_once()
