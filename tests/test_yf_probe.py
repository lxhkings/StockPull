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
def test_probe_intraday_other_exception_is_error(mock_dl):
    from apis.yfinance.probe import probe_intraday

    mock_dl.side_effect = RuntimeError("boom")
    latest, status = probe_intraday("15m")
    assert latest is None
    assert status == "error"


@patch("apis.yfinance.probe.download_with_retry")
def test_probe_daily_rate_limit(mock_dl):
    from apis.yfinance.probe import probe_daily

    mock_dl.side_effect = Exception("RateLimit")
    status = probe_daily(date(2026, 7, 10))
    assert status == "rate_limit"


@patch("apis.yfinance.probe.download_with_retry")
def test_probe_weekly_rate_limit(mock_dl):
    from apis.yfinance.probe import probe_weekly

    mock_dl.side_effect = Exception("Too Many Requests")
    status = probe_weekly(date(2026, 7, 6))
    assert status == "rate_limit"


@patch("apis.yfinance.probe.download_with_retry")
def test_probe_daily_hit_target_date(mock_dl):
    from apis.yfinance.probe import probe_daily

    idx = pd.DatetimeIndex([pd.Timestamp("2026-07-10")], name="Date")
    mock_dl.return_value = pd.DataFrame(
        {"Open": [1.0], "High": [1.0], "Low": [1.0], "Close": [1.0], "Volume": [1]},
        index=idx,
    )
    status = probe_daily(date(2026, 7, 10))
    assert status == "ok"
    assert mock_dl.call_args.kwargs.get("timeout") is not None
    from config import YF_TIMEOUT
    assert mock_dl.call_args.kwargs["timeout"] == YF_TIMEOUT


@patch("apis.yfinance.probe.download_with_retry")
def test_probe_daily_miss_target_date(mock_dl):
    from apis.yfinance.probe import probe_daily

    idx = pd.DatetimeIndex([pd.Timestamp("2026-07-09")], name="Date")
    mock_dl.return_value = pd.DataFrame(
        {"Open": [1.0], "High": [1.0], "Low": [1.0], "Close": [1.0], "Volume": [1]},
        index=idx,
    )
    status = probe_daily(date(2026, 7, 10))
    assert status == "no_data"


@patch("apis.yfinance.probe.download_with_retry")
def test_probe_daily_empty_is_no_data(mock_dl):
    from apis.yfinance.probe import probe_daily

    mock_dl.return_value = pd.DataFrame()
    assert probe_daily(date(2026, 7, 10)) == "no_data"


@patch("apis.yfinance.probe.download_with_retry")
def test_probe_weekly_hit_target_monday(mock_dl):
    from apis.yfinance.probe import probe_weekly

    idx = pd.DatetimeIndex([pd.Timestamp("2026-07-06")], name="Date")
    mock_dl.return_value = pd.DataFrame(
        {"Open": [1.0], "High": [1.0], "Low": [1.0], "Close": [1.0], "Volume": [1]},
        index=idx,
    )
    assert probe_weekly(date(2026, 7, 6)) == "ok"
