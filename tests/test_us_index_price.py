"""Tests for US market index/ETF price fetching."""

from datetime import date
from unittest.mock import patch

import pandas as pd


def test_us_index_symbols_include_sector_etfs():
    """US_INDEX_SYMBOLS covers QQQ + 11 GICS sector ETFs."""
    from apis.yfinance.prices_index import US_INDEX_SYMBOLS

    ids = {index_id for _, index_id in US_INDEX_SYMBOLS}
    expected = {
        "SP500", "RUSSELL1000", "QQQ",
        "XLK", "XLY", "XLF", "XLV", "XLP",
        "XLI", "XLE", "XLB", "XLRE", "XLU", "XLC",
    }
    assert expected <= ids


def test_us_index_symbols_tuple_format():
    from apis.yfinance.prices_index import US_INDEX_SYMBOLS
    for symbol, index_id in US_INDEX_SYMBOLS:
        assert isinstance(symbol, str) and symbol
        assert isinstance(index_id, str) and index_id
    assert ("XLK", "XLK") in US_INDEX_SYMBOLS
    assert ("^GSPC", "SP500") in US_INDEX_SYMBOLS


def test_market_us_update_index_price_delegates():
    from jobs import market_us

    with patch("jobs.market_us.update_index_prices", return_value=7) as mock_upd:
        assert market_us.update_index_price() == 7
    mock_upd.assert_called_once_with()


def _yf_daily_df(dates, closes):
    """Mimic yfinance 1d download: DatetimeIndex + Close (pre reset_index/lower)."""
    return pd.DataFrame(
        {"Close": closes},
        index=pd.DatetimeIndex([pd.Timestamp(d) for d in dates], name="Date"),
    )


@patch("apis.yfinance.prices_index.execute")
@patch("apis.yfinance.prices_index.download_with_retry")
@patch("apis.yfinance.prices_index.query")
@patch("apis.yfinance.prices_index.last_us_trading_date", return_value=date(2026, 7, 10))
@patch(
    "apis.yfinance.prices_index.US_INDEX_SYMBOLS",
    [("^GSPC", "SP500")],
)
def test_update_index_prices_skips_when_up_to_date(
    mock_ltd, mock_query, mock_dl, mock_ex
):
    from apis.yfinance.prices_index import update_index_prices

    mock_query.return_value = [{"d": date(2026, 7, 10)}]
    assert update_index_prices() == 0
    mock_dl.assert_not_called()
    mock_ex.assert_not_called()


@patch("apis.yfinance.prices_index.execute", return_value=1)
@patch("apis.yfinance.prices_index.download_with_retry")
@patch("apis.yfinance.prices_index.query")
@patch("apis.yfinance.prices_index.last_us_trading_date", return_value=date(2026, 7, 11))
@patch(
    "apis.yfinance.prices_index.US_INDEX_SYMBOLS",
    [("^GSPC", "SP500")],
)
def test_update_index_prices_inserts_incremental_rows(
    mock_ltd, mock_query, mock_dl, mock_ex
):
    from apis.yfinance.prices_index import update_index_prices

    mock_query.return_value = [{"d": date(2026, 7, 10)}]
    mock_dl.return_value = _yf_daily_df(
        ["2026-07-10", "2026-07-11"], [5000.0, 5010.0]
    )

    n = update_index_prices()
    assert n == 1
    mock_dl.assert_called_once()
    mock_ex.assert_called_once()
    sql, rows = mock_ex.call_args[0][0], mock_ex.call_args[0][1]
    assert "INSERT IGNORE INTO index_prices" in sql
    # only date > last_date
    assert len(rows) == 1
    assert rows[0][0] == date(2026, 7, 11)
    assert rows[0][1] == "SP500"
    assert rows[0][2] == 5010.0


@patch("apis.yfinance.prices_index.execute")
@patch("apis.yfinance.prices_index.download_with_retry")
@patch("apis.yfinance.prices_index.query")
@patch("apis.yfinance.prices_index.last_us_trading_date", return_value=date(2026, 7, 11))
@patch(
    "apis.yfinance.prices_index.US_INDEX_SYMBOLS",
    [("^GSPC", "SP500"), ("QQQ", "QQQ")],
)
def test_update_index_prices_skips_symbol_on_download_error(
    mock_ltd, mock_query, mock_dl, mock_ex
):
    from apis.yfinance.prices_index import update_index_prices

    mock_query.return_value = [{"d": None}]
    mock_dl.side_effect = [
        Exception("network"),
        _yf_daily_df(["2026-07-11"], [400.0]),
    ]
    mock_ex.return_value = 1

    n = update_index_prices()
    assert n == 1
    assert mock_dl.call_count == 2
    mock_ex.assert_called_once()
