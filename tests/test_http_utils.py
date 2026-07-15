"""http_utils.py 纯函数测试：fetch_with_retry / fetch_urls_sequentially / to_float / to_int / format_cik。"""
from unittest.mock import patch, MagicMock

import pytest
import requests

from core.http_utils import (
    fetch_with_retry,
    fetch_urls_sequentially,
    to_float,
    to_int,
    to_date,
    format_cik,
    or_none,
)
import pandas as pd


# ── fetch_with_retry ──────────────────────────────────────────────

def test_fetch_with_retry_succeeds_first_attempt():
    resp = MagicMock(spec=requests.Response)
    with patch("core.http_utils.requests.get", return_value=resp) as mock_get, \
         patch("core.http_utils.time.sleep") as mock_sleep:
        result = fetch_with_retry("http://example.com")
    assert result is resp
    mock_get.assert_called_once()
    mock_sleep.assert_not_called()


def test_fetch_with_retry_retries_then_succeeds():
    resp = MagicMock(spec=requests.Response)
    mock_get = MagicMock(side_effect=[ConnectionError("boom"), resp])
    with patch("core.http_utils.requests.get", mock_get), \
         patch("core.http_utils.time.sleep") as mock_sleep:
        result = fetch_with_retry("http://example.com", max_retries=3)
    assert result is resp
    assert mock_get.call_count == 2
    assert mock_sleep.call_count == 1


def test_fetch_with_retry_exhausts_and_raises():
    mock_get = MagicMock(side_effect=ConnectionError("final"))
    with patch("core.http_utils.requests.get", mock_get), \
         patch("core.http_utils.time.sleep") as mock_sleep:
        with pytest.raises(ConnectionError):
            fetch_with_retry("http://example.com", max_retries=2)
    assert mock_get.call_count == 2
    assert mock_sleep.call_count == 1  # no sleep after final


# ── fetch_urls_sequentially ───────────────────────────────────────

def test_fetch_urls_sequentially_first_url_succeeds():
    resp = MagicMock(spec=requests.Response)
    with patch("core.http_utils.requests.get", return_value=resp) as mock_get:
        result = fetch_urls_sequentially(["http://a.com", "http://b.com"])
    assert result is resp
    assert mock_get.call_count == 1
    assert mock_get.call_args.kwargs["timeout"] == 30


def test_fetch_urls_sequentially_falls_back_to_second():
    resp = MagicMock(spec=requests.Response)
    mock_get = MagicMock(side_effect=[ConnectionError("fail"), resp])
    with patch("core.http_utils.requests.get", mock_get):
        result = fetch_urls_sequentially(["http://a.com", "http://b.com"])
    assert result is resp
    assert mock_get.call_count == 2


def test_fetch_urls_sequentially_all_fail_returns_none():
    mock_get = MagicMock(side_effect=ConnectionError("all fail"))
    with patch("core.http_utils.requests.get", mock_get):
        result = fetch_urls_sequentially(["http://a.com", "http://b.com"])
    assert result is None


# ── to_float ──────────────────────────────────────────────────────

def test_to_float_normal():
    assert to_float("3.14") == 3.14
    assert to_float(42) == 42.0


def test_to_float_none():
    assert to_float(None) is None


def test_to_float_nan_string():
    assert to_float("nan") is None


def test_to_float_invalid():
    assert to_float("abc") is None


# ── to_int ────────────────────────────────────────────────────────

def test_to_int_normal():
    assert to_int("42") == 42
    assert to_int(3.14) == 3


def test_to_int_none():
    assert to_int(None) is None


def test_to_int_invalid():
    assert to_int("abc") is None


# ── format_cik ────────────────────────────────────────────────────

def test_format_cik_normal():
    assert format_cik(7890) == "0000007890"
    assert format_cik("320193") == "0000320193"


def test_format_cik_none():
    assert format_cik(None) is None


def test_format_cik_nan():
    assert format_cik("nan") is None


def test_format_cik_empty():
    assert format_cik("") is None


def test_format_cik_invalid():
    assert format_cik("abc") is None


# ── to_date ───────────────────────────────────────────────────────

def test_to_date_converts_yyyymmdd():
    assert to_date("20240403") == "2024-04-03"


def test_to_date_handles_none_and_nan():
    assert to_date(None) is None
    assert to_date(float("nan")) is None


def test_to_date_handles_empty_string():
    assert to_date("") is None


def test_to_date_passes_through_non_8_char_string():
    assert to_date("2024-04-03") == "2024-04-03"


# ── or_none ───────────────────────────────────────────────────────

def test_or_none_none_and_nan():
    assert or_none(None) is None
    assert or_none(float("nan")) is None
    assert or_none(pd.NA) is None


def test_or_none_passthrough():
    assert or_none("沪深300ETF") == "沪深300ETF"
    assert or_none(0) == 0
    assert or_none("") == ""

