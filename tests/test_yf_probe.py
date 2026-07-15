"""Contract canaries for apis.yfinance.probe."""
from datetime import date
from unittest.mock import patch

import pandas as pd


@patch("apis.yfinance.probe.download_with_retry")
def test_probe_intraday_rate_limit(mock_dl):
    from apis.yfinance.probe import probe_intraday

    mock_dl.side_effect = Exception("Too Many Requests")
    latest, status = probe_intraday("1h")
    assert latest is None
    assert status == "rate_limit"


@patch("apis.yfinance.probe.download_with_retry")
def test_probe_intraday_empty_is_no_data(mock_dl):
    from apis.yfinance.probe import probe_intraday

    mock_dl.return_value = pd.DataFrame()
    latest, status = probe_intraday("1h")
    assert latest is None
    assert status == "no_data"


@patch("apis.yfinance.probe.download_with_retry")
def test_probe_daily_rate_limit(mock_dl):
    from apis.yfinance.probe import probe_daily

    mock_dl.side_effect = Exception("RateLimit")
    df, status = probe_daily(date(2026, 7, 10))
    assert df is None
    assert status == "rate_limit"


@patch("apis.yfinance.probe.download_with_retry")
def test_probe_weekly_rate_limit(mock_dl):
    from apis.yfinance.probe import probe_weekly

    mock_dl.side_effect = Exception("Too Many Requests")
    df, status = probe_weekly(date(2026, 7, 6))
    assert df is None
    assert status == "rate_limit"


@patch("apis.yfinance.probe.download_with_retry")
def test_probe_intraday_other_exception_is_error(mock_dl):
    from apis.yfinance.probe import probe_intraday

    mock_dl.side_effect = RuntimeError("boom")
    latest, status = probe_intraday("15m")
    assert latest is None
    assert status == "error"
