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