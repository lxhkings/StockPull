"""Tests for market_us.intraday()"""
from unittest.mock import patch


def test_intraday_default_calls_1h():
    with patch("data.intraday_updater_us.update_intraday") as mock_update:
        mock_update.return_value = {"AAPL": "ok"}
        from data import market_us
        result = market_us.intraday()
    mock_update.assert_called_once_with("1h")
    assert result == {"AAPL": "ok"}


def test_intraday_custom_intervals():
    with patch("data.intraday_updater_us.update_intraday") as mock_update:
        mock_update.return_value = {"AAPL": "ok"}
        from data import market_us
        result = market_us.intraday(["15m", "1h"])
    assert mock_update.call_count == 2
    mock_update.assert_any_call("15m")
    mock_update.assert_any_call("1h")


def test_intraday_merges_results():
    def side_effect(ivl):
        return {"AAPL": "ok"} if ivl == "1h" else {"AAPL": "no_data"}

    with patch("data.intraday_updater_us.update_intraday", side_effect=side_effect):
        from data import market_us
        result = market_us.intraday(["15m", "1h"])
    # second call overwrites first — last interval wins for same ticker
    assert result["AAPL"] == "ok"