"""Tests for US market index/ETF price fetching."""


def test_us_index_symbols_include_sector_etfs():
    """US_INDEX_SYMBOLS covers QQQ + 11 GICS sector ETFs."""
    from apis.yfinance.prices_index import US_INDEX_SYMBOLS

    ids = {index_id for _, index_id in US_INDEX_SYMBOLS}
    expected = {
        "SP500", "RUSSELL1000", "QQQ",
        "XLK", "XLY", "XLF", "XLV", "XLP",
        "XLI", "XLE", "XLB", "XLRE", "XLU", "XLC",
    }
    assert expected <= ids


def test_us_index_symbols_tuple_format():
    from apis.yfinance.prices_index import US_INDEX_SYMBOLS
    for symbol, index_id in US_INDEX_SYMBOLS:
        assert isinstance(symbol, str) and symbol
        assert isinstance(index_id, str) and index_id
    assert ("XLK", "XLK") in US_INDEX_SYMBOLS
    assert ("^GSPC", "SP500") in US_INDEX_SYMBOLS


def test_market_us_update_index_price_delegates():
    from unittest.mock import patch
    from jobs import market_us

    with patch("jobs.market_us.update_index_prices", return_value=7) as mock_upd:
        assert market_us.update_index_price() == 7
    mock_upd.assert_called_once_with()
