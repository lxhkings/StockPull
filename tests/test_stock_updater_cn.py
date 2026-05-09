# tests/test_stock_updater_cn.py
from unittest.mock import patch, MagicMock
import pandas as pd
from datetime import date


def _ak_hist_df():
    return pd.DataFrame({
        "日期":     ["2024-01-02", "2024-01-03"],
        "开盘":     [1700.0, 1710.0],
        "收盘":     [1715.0, 1720.0],
        "最高":     [1720.0, 1725.0],
        "最低":     [1695.0, 1705.0],
        "成交量":   [1000000, 1100000],
        "成交额":   [1.7e9, 1.8e9],
    })


@patch("data.stock_updater_cn.ak.stock_zh_a_hist")
def test_fetch_one_normalizes_columns(mock_ak):
    from data.stock_updater_cn import _fetch_one_akshare
    mock_ak.return_value = _ak_hist_df()
    df = _fetch_one_akshare("600519.SH", date(2024, 1, 1), date(2024, 1, 5))
    assert list(df.columns) == ["ticker", "date", "open", "high", "low", "close", "volume"]
    assert df["ticker"].iloc[0] == "600519.SH"
    assert df["date"].iloc[0] == date(2024, 1, 2)
    assert df["close"].iloc[1] == 1720.0


@patch("data.stock_updater_cn._fetch_one_akshare")
@patch("data.stock_updater_cn.get_conn")
def test_update_prices_writes_and_logs(mock_get_conn, mock_fetch):
    from data.stock_updater_cn import update_prices_batch
    mock_fetch.return_value = pd.DataFrame({
        "ticker": ["600519.SH"], "date": [date(2024, 1, 2)],
        "open": [1700.0], "high": [1720.0], "low": [1695.0],
        "close": [1715.0], "volume": [1000000],
    })
    cur = MagicMock()
    cur.fetchone.return_value = None
    mock_get_conn.return_value.cursor.return_value.__enter__.return_value = cur

    result = update_prices_batch(["600519.SH"])
    assert result["600519.SH"] == "ok"


@patch("data.stock_updater_cn._fetch_one_efinance")
@patch("data.stock_updater_cn._fetch_one_akshare")
@patch("data.stock_updater_cn.get_conn")
def test_backfill_calls_both_sources_and_reconciles(mock_conn, mock_ak, mock_ef):
    from data.stock_updater_cn import update_prices_batch
    mock_ak.return_value = pd.DataFrame({
        "ticker": ["600519.SH"], "date": [date(2024, 1, 2)],
        "open": [1700.0], "high": [1720.0], "low": [1695.0],
        "close": [1715.0], "volume": [1000000],
    })
    mock_ef.return_value = pd.DataFrame({
        "ticker": ["600519.SH"], "date": [date(2024, 1, 2)],
        "open": [1700.5], "high": [1721.0], "low": [1696.0],
        "close": [1715.3], "volume": [1000100],
    })
    cur = MagicMock()
    cur.fetchone.return_value = None  # last_sync = None → backfill mode
    mock_conn.return_value.cursor.return_value.__enter__.return_value = cur

    result = update_prices_batch(["600519.SH"])
    assert result["600519.SH"] == "ok"
    mock_ef.assert_called_once()  # backfill triggers efinance
