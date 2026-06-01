from scripts.probe_futu_limits import classify, summarize_rounds


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


def test_summarize_takes_min_and_computes_intervals():
    r = summarize_rounds("get_company_profile", [32, 30, 31], raw_msg="too frequent")
    assert r["interface"] == "get_company_profile"
    assert r["n_per_30s"] == 30
    assert r["status"] == "OK"
    assert round(r["fastest_interval"], 3) == round(30 / 30, 3)        # 1.0
    assert round(r["recommended_interval"], 3) == round(30 / (30 * 0.8), 3)  # 1.25
    assert r["raw_msg"] == "too frequent"


def test_summarize_no_limit_hit_at_cap():
    r = summarize_rounds("get_market_snapshot", [120, 120, 120], raw_msg="no-limit-hit@cap")
    assert r["status"] == "NO-LIMIT@cap"
    assert r["n_per_30s"] == 120


def test_summarize_skip_on_negative():
    # -1 表示 OTHER(不可测),任一轮为 -1 即 SKIP
    r = summarize_rounds("get_insider_trade_list", [-1], raw_msg="no data")
    assert r["status"] == "SKIP"
    assert r["n_per_30s"] is None
    assert r["fastest_interval"] is None
    assert r["recommended_interval"] is None


def test_summarize_zero_no_division_error():
    # n=0 表示首轮即 FREQ,不应触发除零
    r = summarize_rounds("get_market_snapshot", [0, 0, 0], raw_msg="too frequent")
    assert r["status"] == "FREQ@0"
    assert r["n_per_30s"] == 0
    assert r["fastest_interval"] is None
    assert r["recommended_interval"] is None
