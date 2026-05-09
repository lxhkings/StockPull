import pytest

from data.ticker_utils import (
    parse_ticker,
    to_akshare_a,
    to_akshare_hk,
    to_yfinance_us,
    infer_market,
    Market,
)


@pytest.mark.parametrize("ticker,code,suffix", [
    ("600519.SH", "600519", "SH"),
    ("000001.SZ", "000001", "SZ"),
    ("00700.HK", "00700", "HK"),
    ("AAPL", "AAPL", None),
    ("BRK-B", "BRK-B", None),
])
def test_parse_ticker(ticker, code, suffix):
    p = parse_ticker(ticker)
    assert p.code == code
    assert p.suffix == suffix


@pytest.mark.parametrize("ticker,market", [
    ("AAPL", Market.US),
    ("BRK-B", Market.US),
    ("600519.SH", Market.CN),
    ("000001.SZ", Market.CN),
    ("300750.SZ", Market.CN),
    ("688981.SH", Market.CN),
    ("00700.HK", Market.HK),
    ("09988.HK", Market.HK),
])
def test_infer_market(ticker, market):
    assert infer_market(ticker) == market


def test_to_akshare_a_strips_suffix():
    assert to_akshare_a("600519.SH") == "600519"
    assert to_akshare_a("000001.SZ") == "000001"


def test_to_akshare_a_rejects_non_a():
    with pytest.raises(ValueError):
        to_akshare_a("AAPL")
    with pytest.raises(ValueError):
        to_akshare_a("00700.HK")


def test_to_akshare_hk_strips_and_pads():
    assert to_akshare_hk("00700.HK") == "00700"
    assert to_akshare_hk("09988.HK") == "09988"


def test_to_akshare_hk_rejects_non_hk():
    with pytest.raises(ValueError):
        to_akshare_hk("600519.SH")


def test_to_yfinance_us_dot_to_dash():
    """yfinance: BRK.B → BRK-B."""
    assert to_yfinance_us("AAPL") == "AAPL"
    assert to_yfinance_us("BRK.B") == "BRK-B"
