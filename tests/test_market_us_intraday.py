"""Tests for market_us.intraday()"""
from unittest.mock import patch, call


def test_intraday_default_uses_supported_intervals():
    with patch("apis.yfinance.prices_intraday.update_intraday") as mock_update, \
         patch("apis.yfinance.prices_intraday.SUPPORTED_INTERVALS", ["15m", "1h"]), \
         patch("jobs.market_us.list_active_tickers", return_value=["AAPL"]):
        mock_update.return_value = {"AAPL": "ok"}
        from jobs import market_us
        result = market_us.intraday()
    assert mock_update.call_count == 2
    mock_update.assert_has_calls([
        call("15m", full_rebase=False, tickers=["AAPL"]),
        call("1h", full_rebase=False, tickers=["AAPL"]),
    ])
    assert result == {"AAPL": "ok"}


def test_intraday_custom_intervals():
    with patch("apis.yfinance.prices_intraday.update_intraday") as mock_update, \
         patch("jobs.market_us.list_active_tickers", return_value=["AAPL"]):
        mock_update.return_value = {"AAPL": "ok"}
        from jobs import market_us
        result = market_us.intraday(["15m", "1h"])
    assert mock_update.call_count == 2
    mock_update.assert_any_call("15m", full_rebase=False, tickers=["AAPL"])
    mock_update.assert_any_call("1h", full_rebase=False, tickers=["AAPL"])


def test_intraday_full_rebase_forwarded():
    with patch("apis.yfinance.prices_intraday.update_intraday") as mock_update, \
         patch("jobs.market_us.list_active_tickers", return_value=["AAPL", "MSFT"]):
        mock_update.return_value = {}
        from jobs import market_us
        market_us.intraday(["1h"], full_rebase=True)
    mock_update.assert_called_once_with(
        "1h", full_rebase=True, tickers=["AAPL", "MSFT"]
    )


def test_intraday_merges_results():
    def side_effect(ivl, full_rebase=False, tickers=None):
        return {"AAPL": "ok"} if ivl == "1h" else {"AAPL": "no_data"}

    with patch("apis.yfinance.prices_intraday.update_intraday", side_effect=side_effect), \
         patch("jobs.market_us.list_active_tickers", return_value=["AAPL"]):
        from jobs import market_us
        result = market_us.intraday(["15m", "1h"])
    # second call overwrites first — last interval wins for same ticker
    assert result["AAPL"] == "ok"
