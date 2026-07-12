# tests/test_yf_client.py
from unittest.mock import patch, MagicMock
import pandas as pd
import pytest


def test_download_with_retry_success_first_attempt():
    from apis.yfinance.client import download_with_retry
    df = pd.DataFrame({"Close": [1.0]})
    with patch("apis.yfinance.client.yf.download", return_value=df) as mock_dl, \
         patch("core.retry_utils.time.sleep") as mock_sleep:
        result = download_with_retry(
            tickers=["AAPL"], start="2026-01-01", end="2026-01-02", interval="1d",
        )
    assert result is df
    mock_dl.assert_called_once()
    mock_sleep.assert_not_called()


def test_download_with_retry_passes_kwargs_through():
    from apis.yfinance.client import download_with_retry
    with patch("apis.yfinance.client.yf.download", return_value=pd.DataFrame()) as mock_dl:
        download_with_retry(
            tickers=["AAPL", "MSFT"], start="2026-01-01", end="2026-01-02",
            interval="1wk", group_by="ticker", threads=False, repair=False,
        )
    kwargs = mock_dl.call_args.kwargs
    assert kwargs["tickers"] == ["AAPL", "MSFT"]
    assert kwargs["interval"] == "1wk"
    assert kwargs["group_by"] == "ticker"
    assert kwargs["threads"] is False
    assert kwargs["repair"] is False
    assert kwargs["auto_adjust"] is False
    assert kwargs["actions"] is False
    assert kwargs["progress"] is False


def test_download_with_retry_omits_repair_when_not_given():
    from apis.yfinance.client import download_with_retry
    with patch("apis.yfinance.client.yf.download", return_value=pd.DataFrame()) as mock_dl:
        download_with_retry(
            tickers=["AAPL"], start="2026-01-01", end="2026-01-02", interval="15m",
        )
    assert "repair" not in mock_dl.call_args.kwargs


def test_download_with_retry_retries_then_succeeds():
    from apis.yfinance.client import download_with_retry
    df = pd.DataFrame({"Close": [1.0]})
    with patch("apis.yfinance.client.yf.download", side_effect=[ConnectionError("boom"), df]) as mock_dl, \
         patch("core.retry_utils.time.sleep") as mock_sleep:
        result = download_with_retry(
            tickers=["AAPL"], start="2026-01-01", end="2026-01-02", interval="1d",
            retry_count=3,
        )
    assert result is df
    assert mock_dl.call_count == 2
    mock_sleep.assert_called_once_with(5)  # backoff = 5 * 3**0


def test_download_with_retry_exhausts_and_raises_last_exception():
    from apis.yfinance.client import download_with_retry
    err1 = ConnectionError("first")
    err2 = TimeoutError("second")
    with patch("apis.yfinance.client.yf.download", side_effect=[err1, err2]) as mock_dl, \
         patch("core.retry_utils.time.sleep") as mock_sleep:
        with pytest.raises(TimeoutError) as exc_info:
            download_with_retry(
                tickers=["AAPL"], start="2026-01-01", end="2026-01-02", interval="1d",
                retry_count=2,
            )
    assert exc_info.value is err2
    assert mock_dl.call_count == 2
    mock_sleep.assert_called_once_with(5)  # only 1 sleep: no sleep after final attempt


def test_download_with_retry_uses_config_defaults():
    from apis.yfinance.client import download_with_retry
    import config
    with patch("apis.yfinance.client.yf.download", return_value=pd.DataFrame()) as mock_dl:
        download_with_retry(
            tickers=["AAPL"], start="2026-01-01", end="2026-01-02", interval="1d",
        )
    assert mock_dl.call_args.kwargs["timeout"] == config.YF_TIMEOUT
    assert mock_dl.call_args.kwargs["threads"] == config.YF_THREADS


# ── history_with_retry (yf.Ticker(...).history()) ──────────────────────────

def test_history_with_retry_success_first_attempt():
    from apis.yfinance.client import history_with_retry
    df = pd.DataFrame({"Close": [1.0]})
    mock_ticker = MagicMock()
    mock_ticker.history.return_value = df
    with patch("apis.yfinance.client.yf.Ticker", return_value=mock_ticker) as mock_tk, \
         patch("core.retry_utils.time.sleep") as mock_sleep:
        result = history_with_retry("00700.HK", start="2026-01-01", end="2026-01-02")
    assert result is df
    mock_tk.assert_called_once_with("00700.HK")
    mock_ticker.history.assert_called_once_with(start="2026-01-01", end="2026-01-02")
    mock_sleep.assert_not_called()


def test_history_with_retry_retries_then_succeeds():
    from apis.yfinance.client import history_with_retry
    df = pd.DataFrame({"Close": [1.0]})
    mock_ticker = MagicMock()
    mock_ticker.history.side_effect = [ConnectionError("boom"), df]
    with patch("apis.yfinance.client.yf.Ticker", return_value=mock_ticker), \
         patch("core.retry_utils.time.sleep") as mock_sleep:
        result = history_with_retry("00700.HK", start="2026-01-01", end="2026-01-02", retry_count=3)
    assert result is df
    assert mock_ticker.history.call_count == 2
    mock_sleep.assert_called_once_with(5)


def test_history_with_retry_exhausts_and_raises_last_exception():
    from apis.yfinance.client import history_with_retry
    err1 = ConnectionError("first")
    err2 = TimeoutError("second")
    mock_ticker = MagicMock()
    mock_ticker.history.side_effect = [err1, err2]
    with patch("apis.yfinance.client.yf.Ticker", return_value=mock_ticker), \
         patch("core.retry_utils.time.sleep"):
        with pytest.raises(TimeoutError) as exc_info:
            history_with_retry("00700.HK", start="2026-01-01", end="2026-01-02", retry_count=2)
    assert exc_info.value is err2
