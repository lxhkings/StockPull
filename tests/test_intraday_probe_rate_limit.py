"""Intraday AAPL probe rate_limit alignment with daily/weekly probes."""
from unittest.mock import patch

import pandas as pd


@patch("apis.yfinance.prices_intraday.download_with_retry")
def test_test_aapl_intraday_rate_limit_from_exception(mock_dl):
    from apis.yfinance.prices_intraday import _test_aapl_intraday

    mock_dl.side_effect = Exception("YFRateLimitError: Too Many Requests")
    latest, status = _test_aapl_intraday("1h")
    assert latest is None
    assert status == "rate_limit"


@patch("apis.yfinance.prices_intraday.download_with_retry")
def test_test_aapl_intraday_empty_is_no_data_not_rate_limit(mock_dl):
    from apis.yfinance.prices_intraday import _test_aapl_intraday

    mock_dl.return_value = pd.DataFrame()
    latest, status = _test_aapl_intraday("1h")
    assert latest is None
    assert status == "no_data"


@patch("apis.yfinance.prices_intraday.download_with_retry")
def test_test_aapl_intraday_other_exception_is_error(mock_dl):
    from apis.yfinance.prices_intraday import _test_aapl_intraday

    mock_dl.side_effect = RuntimeError("boom")
    latest, status = _test_aapl_intraday("15m")
    assert latest is None
    assert status == "error"


@patch("apis.yfinance.prices_intraday.get_index_tickers")
@patch("apis.yfinance.prices_intraday._test_aapl_intraday")
def test_update_intraday_skips_on_rate_limit(mock_probe, mock_tickers):
    from apis.yfinance.prices_intraday import update_intraday

    mock_probe.return_value = (None, "rate_limit")
    mock_tickers.return_value = ["AAPL"]
    result = update_intraday("1h")
    assert result == {}
    # must not proceed to ticker universe work beyond probe
    mock_tickers.assert_not_called()
