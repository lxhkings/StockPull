from apis.tushare.ticker_map import (
    index_id_to_ts_code,
    is_a_share, is_hk, is_us,
    ts_code_to_canonical,
)


def test_index_mapping():
    assert index_id_to_ts_code("CSI800") == "000906.SH"
    assert index_id_to_ts_code("HSI") == "HSI"
    assert index_id_to_ts_code("SP500") == "SPX"


def test_market_classifier_a_share():
    assert is_a_share("600519.SH") is True
    assert is_a_share("000001.SZ") is True
    assert is_a_share("00700.HK") is False


def test_market_classifier_hk():
    assert is_hk("00700.HK") is True
    assert is_hk("AAPL") is False


def test_market_classifier_us():
    assert is_us("AAPL") is True
    assert is_us("BRK.B") is True
    assert is_us("600519.SH") is False


def test_ts_code_to_canonical_passthrough():
    assert ts_code_to_canonical("600519.SH") == "600519.SH"
    assert ts_code_to_canonical("00700.HK") == "00700.HK"
    assert ts_code_to_canonical("AAPL") == "AAPL"
