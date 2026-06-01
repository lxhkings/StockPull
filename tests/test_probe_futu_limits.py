from scripts.probe_futu_limits import classify


def test_classify_ok():
    assert classify(0, "anything") == "OK"


def test_classify_freq_chinese():
    assert classify(-1, "请求过于频繁，请稍后再试") == "FREQ"


def test_classify_freq_english():
    assert classify(-1, "request too frequent") == "FREQ"


def test_classify_freq_limit_keyword():
    assert classify(-1, "接口限频，30秒内最多N次") == "FREQ"


def test_classify_other_no_data():
    assert classify(-1, "no data found for US.AAPL") == "OTHER"


def test_classify_other_no_permission():
    assert classify(-1, "no quote right / 无权限") == "OTHER"
