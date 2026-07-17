"""Intraday AAPL probe rate_limit alignment with daily/weekly probes."""
from unittest.mock import patch

import pandas as pd


@patch("apis.yfinance.probe.download_with_retry")
def test_probe_intraday_rate_limit_from_exception(mock_dl):
    from apis.yfinance.probe import probe_intraday

    mock_dl.side_effect = Exception("YFRateLimitError: Too Many Requests")
    latest, status = probe_intraday("1h")
    assert latest is None
    assert status == "rate_limit"


@patch("apis.yfinance.probe.download_with_retry")
def test_probe_intraday_empty_is_no_data_not_rate_limit(mock_dl):
    from apis.yfinance.probe import probe_intraday

    mock_dl.return_value = pd.DataFrame()
    latest, status = probe_intraday("1h")
    assert latest is None
    assert status == "no_data"


@patch("apis.yfinance.probe.download_with_retry")
def test_probe_intraday_other_exception_is_error(mock_dl):
    from apis.yfinance.probe import probe_intraday

    mock_dl.side_effect = RuntimeError("boom")
    latest, status = probe_intraday("15m")
    assert latest is None
    assert status == "error"


@patch("apis.yfinance.prices_intraday_batch.get_index_tickers")
@patch("apis.yfinance.prices_intraday_batch.probe_intraday")
def test_update_intraday_skips_on_rate_limit(mock_probe, mock_tickers):
    from apis.yfinance.prices_intraday import update_intraday

    mock_probe.return_value = (None, "rate_limit")
    mock_tickers.return_value = ["AAPL"]
    result = update_intraday("1h")
    assert result == {}
    # must not proceed to ticker universe work beyond probe
    mock_tickers.assert_not_called()
