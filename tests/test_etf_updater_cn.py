"""Tests for CN sector ETF hfq close fetching via tushare."""
import pytest
from unittest.mock import patch, MagicMock
import pandas as pd
from datetime import date


@patch("data.etf_updater_cn.get_client")
def test_fetch_etf_daily_hfq_merges_close_and_adj(mock_get_client):
    """hfq_close = raw close × adj_factor, merged on trade_date."""
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client

    daily_df = pd.DataFrame({
        "ts_code": ["512800.SH", "512800.SH"],
        "trade_date": ["20260513", "20260512"],
        "close": [1.500, 1.480],
    })
    adj_df = pd.DataFrame({
        "ts_code": ["512800.SH", "512800.SH"],
        "trade_date": ["20260513", "20260512"],
        "adj_factor": [1.20, 1.20],
    })

    def fake_call(api, **kwargs):
        if api == "fund_daily":
            return daily_df
        if api == "fund_adj":
            return adj_df
        raise AssertionError(f"unexpected api: {api}")

    mock_client.call.side_effect = fake_call

    from data.etf_updater_cn import fetch_etf_daily_hfq
    df = fetch_etf_daily_hfq("512800.SH", start_date=None)

    assert list(df.columns) == ["date", "hfq_close"]
    assert len(df) == 2
    # Sorted ascending by date
    assert df.iloc[0]["date"] == date(2026, 5, 12)
    assert df.iloc[0]["hfq_close"] == pytest.approx(1.480 * 1.20)
    assert df.iloc[1]["date"] == date(2026, 5, 13)
    assert df.iloc[1]["hfq_close"] == pytest.approx(1.500 * 1.20)


@patch("data.etf_updater_cn.get_client")
def test_fetch_etf_daily_hfq_empty_when_no_daily(mock_get_client):
    """Empty fund_daily → empty DataFrame, fund_adj not called."""
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    mock_client.call.return_value = pd.DataFrame()

    from data.etf_updater_cn import fetch_etf_daily_hfq
    df = fetch_etf_daily_hfq("512800.SH", start_date=None)

    assert df.empty
    # Only fund_daily called, not fund_adj (early return)
    assert mock_client.call.call_count == 1
    assert mock_client.call.call_args[0][0] == "fund_daily"


@patch("data.etf_updater_cn.get_client")
def test_fetch_etf_daily_hfq_handles_missing_adj(mock_get_client):
    """Empty fund_adj → fallback to raw close."""
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client

    daily_df = pd.DataFrame({
        "ts_code": ["512800.SH"],
        "trade_date": ["20260513"],
        "close": [1.500],
    })

    def fake_call(api, **kwargs):
        if api == "fund_daily":
            return daily_df
        if api == "fund_adj":
            return pd.DataFrame()
        raise AssertionError(api)

    mock_client.call.side_effect = fake_call

    from data.etf_updater_cn import fetch_etf_daily_hfq
    df = fetch_etf_daily_hfq("512800.SH", start_date=None)

    assert len(df) == 1
    assert df.iloc[0]["hfq_close"] == pytest.approx(1.500)


@patch("data.etf_updater_cn.get_client")
def test_fetch_etf_daily_hfq_ffill_adj_gaps(mock_get_client):
    """Missing adj_factor rows are forward-filled."""
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client

    daily_df = pd.DataFrame({
        "ts_code": ["512800.SH"] * 3,
        "trade_date": ["20260511", "20260512", "20260513"],
        "close": [1.0, 1.1, 1.2],
    })
    # adj only on 20260511 and 20260513, 20260512 missing
    adj_df = pd.DataFrame({
        "ts_code": ["512800.SH", "512800.SH"],
        "trade_date": ["20260511", "20260513"],
        "adj_factor": [2.0, 2.5],
    })

    def fake_call(api, **kwargs):
        if api == "fund_daily":
            return daily_df
        if api == "fund_adj":
            return adj_df
        raise AssertionError(api)

    mock_client.call.side_effect = fake_call

    from data.etf_updater_cn import fetch_etf_daily_hfq
    df = fetch_etf_daily_hfq("512800.SH", start_date=None)

    assert len(df) == 3
    # 20260512 ffills from 20260511 (factor 2.0)
    row_0512 = df[df["date"] == date(2026, 5, 12)].iloc[0]
    assert row_0512["hfq_close"] == pytest.approx(1.1 * 2.0)


@patch("data.etf_updater_cn.CN_SECTOR_ETFS", {"512800.SH": {"name": "银行ETF", "gics": "Financials"}})
@patch("data.etf_updater_cn.query")
@patch("data.etf_updater_cn.execute")
@patch("data.etf_updater_cn.fetch_etf_daily_hfq")
def test_update_etf_prices_writes_to_index_prices(mock_fetch, mock_execute, mock_query):
    """update_etf_prices writes (date, ts_code, hfq_close) rows to index_prices."""
    mock_query.return_value = [{"d": None}]  # no last_date
    mock_fetch.return_value = pd.DataFrame({
        "date": [date(2026, 5, 12), date(2026, 5, 13)],
        "hfq_close": [1.776, 1.800],
    })
    mock_execute.return_value = 2

    from data.etf_updater_cn import update_etf_prices
    total = update_etf_prices()

    assert total == 2
    # fetch called with start_date=20100101 (no last_date)
    mock_fetch.assert_called_once_with("512800.SH", start_date="20100101")

    # execute called with INSERT IGNORE into index_prices
    sql, rows = mock_execute.call_args[0]
    assert "INSERT IGNORE INTO index_prices" in sql
    assert rows == [
        (date(2026, 5, 12), "512800.SH", 1.776),
        (date(2026, 5, 13), "512800.SH", 1.800),
    ]


@patch("data.etf_updater_cn.CN_SECTOR_ETFS", {"512800.SH": {"name": "银行ETF", "gics": "Financials"}})
@patch("data.etf_updater_cn.query")
@patch("data.etf_updater_cn.execute")
@patch("data.etf_updater_cn.fetch_etf_daily_hfq")
def test_update_etf_prices_incremental_skips_existing(mock_fetch, mock_execute, mock_query):
    """last_date in DB → start_date passed as YYYYMMDD, rows ≤ last_date filtered."""
    mock_query.return_value = [{"d": date(2026, 5, 12)}]
    mock_fetch.return_value = pd.DataFrame({
        "date": [date(2026, 5, 12), date(2026, 5, 13)],
        "hfq_close": [1.776, 1.800],
    })
    mock_execute.return_value = 1

    from data.etf_updater_cn import update_etf_prices
    total = update_etf_prices()

    mock_fetch.assert_called_once_with("512800.SH", start_date="20260512")
    # Only 20260513 row written (20260512 == last_date filtered)
    rows = mock_execute.call_args[0][1]
    assert len(rows) == 1
    assert rows[0][0] == date(2026, 5, 13)


@patch("data.etf_updater_cn.CN_SECTOR_ETFS", {
    "512800.SH": {"name": "银行ETF", "gics": "Financials"},
    "512000.SH": {"name": "券商ETF", "gics": "Financials"},
})
@patch("data.etf_updater_cn.query")
@patch("data.etf_updater_cn.execute")
@patch("data.etf_updater_cn.fetch_etf_daily_hfq")
def test_update_etf_prices_continues_on_single_failure(mock_fetch, mock_execute, mock_query):
    """If one ETF fetch raises, others still process."""
    mock_query.return_value = [{"d": None}]

    def fake_fetch(ts_code, start_date):
        if ts_code == "512800.SH":
            raise RuntimeError("tushare boom")
        return pd.DataFrame({
            "date": [date(2026, 5, 13)],
            "hfq_close": [1.0],
        })

    mock_fetch.side_effect = fake_fetch
    mock_execute.return_value = 1

    from data.etf_updater_cn import update_etf_prices
    total = update_etf_prices()

    # 512000.SH succeeded
    assert total == 1
    assert mock_execute.call_count == 1
    written_rows = mock_execute.call_args[0][1]
    assert written_rows[0][1] == "512000.SH"


@patch("data.etf_updater_cn.CN_SECTOR_ETFS", {"512800.SH": {"name": "银行ETF", "gics": "Financials"}})
@patch("data.etf_updater_cn.query")
@patch("data.etf_updater_cn.execute")
@patch("data.etf_updater_cn.fetch_etf_daily_hfq")
def test_update_etf_prices_full_rebase_ignores_last_date(mock_fetch, mock_execute, mock_query):
    """full_rebase=True → start from 20100101 even if last_date exists."""
    mock_query.return_value = [{"d": date(2026, 5, 12)}]
    mock_fetch.return_value = pd.DataFrame({
        "date": [date(2010, 1, 5), date(2026, 5, 13)],
        "hfq_close": [0.5, 1.8],
    })
    mock_execute.return_value = 2

    from data.etf_updater_cn import update_etf_prices
    total = update_etf_prices(full_rebase=True)

    mock_fetch.assert_called_once_with("512800.SH", start_date="20100101")
    # No last_date filter applied → both rows written
    rows = mock_execute.call_args[0][1]
    assert len(rows) == 2