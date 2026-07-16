import pytest

from apis.yfinance.ticker_utils import (
    parse_ticker,
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


def test_to_yfinance_us_dot_to_dash():
    assert to_yfinance_us("AAPL") == "AAPL"
    assert to_yfinance_us("BRK.B") == "BRK-B"
