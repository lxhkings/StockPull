from unittest.mock import patch, MagicMock
import pandas as pd
from datetime import date


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Tushare-based tests
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@patch("data.index_updater_cn.query")
@patch("data.index_updater_cn.get_client")
def test_fetch_csi800_uses_tushare_index_weight(mock_get_client, mock_query):
    """Test that _fetch_csi800 uses tushare index_weight API."""
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client

    # Tushare index_weight returns multi-period data
    raw_df = pd.DataFrame({
        "index_code": ["000906.SH", "000906.SH", "000906.SH", "000906.SH"],
        "con_code": ["600519.SH", "000001.SZ", "600519.SH", "300750.SZ"],
        "trade_date": ["20260513", "20260513", "20260512", "20260512"],
        "weight": [1.5, 0.8, 1.4, 1.2],
    })
    mock_client.call.return_value = raw_df

    # Stocks table has name and sector
    mock_query.return_value = [
        {"ticker": "600519.SH", "name": "贵州茅台", "gics_sector": "食品饮料"},
        {"ticker": "000001.SZ", "name": "平安银行", "gics_sector": "银行"},
        {"ticker": "300750.SZ", "name": "宁德时代", "gics_sector": "电力设备"},
    ]

    from data.index_updater_cn import _fetch_csi800
    df = _fetch_csi800()

    # Verify tushare API called correctly
    mock_client.call.assert_called_once_with("index_weight", index_code="000906.SH")

    # Should only include latest date (20260513) constituents
    assert len(df) == 2
    assert set(df["ticker"]) == {"600519.SH", "000001.SZ"}
    assert df[df["ticker"] == "600519.SH"]["name"].iloc[0] == "贵州茅台"
    assert df[df["ticker"] == "600519.SH"]["sector"].iloc[0] == "食品饮料"


@patch("data.index_updater_cn.query")
@patch("data.index_updater_cn.get_client")
def test_fetch_csi800_handles_missing_stock_info(mock_get_client, mock_query):
    """Test that _fetch_csi800 handles tickers not in stocks table."""
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client

    raw_df = pd.DataFrame({
        "index_code": ["000906.SH"],
        "con_code": ["999999.SH"],
        "trade_date": ["20260513"],
        "weight": [0.5],
    })
    mock_client.call.return_value = raw_df

    # No matching stock in stocks table
    mock_query.return_value = []

    from data.index_updater_cn import _fetch_csi800
    df = _fetch_csi800()

    assert len(df) == 1
    assert df["ticker"].iloc[0] == "999999.SH"
    assert pd.isna(df["name"].iloc[0]) or df["name"].iloc[0] is None
    assert pd.isna(df["sector"].iloc[0]) or df["sector"].iloc[0] is None


@patch("data.index_updater_cn.get_client")
def test_fetch_csi800_handles_empty_response(mock_get_client):
    """Test that _fetch_csi800 handles empty DataFrame from tushare."""
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    mock_client.call.return_value = pd.DataFrame()  # empty

    from data.index_updater_cn import _fetch_csi800
    df = _fetch_csi800()

    assert df.empty
    assert list(df.columns) == ["ticker", "name", "sector"]


@patch("data.index_updater_cn.get_client")
def test_fetch_csi800_handles_none_response(mock_get_client):
    """Test that _fetch_csi800 handles None response from tushare."""
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    mock_client.call.return_value = None

    from data.index_updater_cn import _fetch_csi800
    df = _fetch_csi800()

    assert df.empty
    assert list(df.columns) == ["ticker", "name", "sector"]


@patch("data.index_updater_cn.get_client")
def test_fetch_csi800_handles_missing_columns(mock_get_client):
    """Test that _fetch_csi800 handles response with missing required columns."""
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    # DataFrame missing 'con_code' column
    mock_client.call.return_value = pd.DataFrame({
        "index_code": ["000906.SH"],
        "trade_date": ["20260513"],
    })

    from data.index_updater_cn import _fetch_csi800
    df = _fetch_csi800()

    assert df.empty
    assert list(df.columns) == ["ticker", "name", "sector"]


@patch("data.index_updater_cn._fetch_csi800")
@patch("data.index_updater_cn.get_conn")
def test_update_csi800_skips_when_today_already_done(mock_get_conn, mock_fetch):
    """If snapshot already exists for today, skip without fetching constituents."""
    from data.index_updater_cn import update_csi800

    # Mock connection with proper context manager support
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_cur.fetchone.return_value = (date.today(),)

    # Set up connection context managers
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur
    mock_get_conn.return_value = mock_conn

    update_csi800()
    mock_fetch.assert_not_called()
    mock_conn.close.assert_called_once()
