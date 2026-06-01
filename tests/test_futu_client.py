from unittest.mock import MagicMock, patch

from futu_ingest.client import to_futu_code, from_futu_code


def test_to_futu_code_adds_us_prefix():
    assert to_futu_code("AAPL") == "US.AAPL"
    assert to_futu_code("BRK.B") == "US.BRK.B"


def test_from_futu_code_strips_us_prefix():
    assert from_futu_code("US.AAPL") == "AAPL"
    assert from_futu_code("US.BRK.B") == "BRK.B"


def test_client_call_returns_data_on_ret_ok():
    from futu_ingest.client import FutuClient
    fake_ctx = MagicMock()
    fake_ctx.get_corporate_actions_dividends.return_value = (0, {"dividend_list": []})
    c = FutuClient()
    c._ctx = fake_ctx          # inject, skip real OpenD
    c._limiter_for = MagicMock()   # 跳过真实限频 sleep
    data = c.call("get_corporate_actions_dividends", "US.AAPL")
    assert data == {"dividend_list": []}


def test_client_call_retries_then_raises_on_ret_error():
    from futu_ingest.client import FutuClient
    fake_ctx = MagicMock()
    fake_ctx.get_market_snapshot.return_value = (-1, "permission denied")
    c = FutuClient()
    c._ctx = fake_ctx
    c._limiter_for = MagicMock()   # 跳过真实限频 sleep
    with patch("futu_ingest.client.time.sleep"):
        try:
            c.call("get_market_snapshot", ["US.AAPL"])
            assert False, "should raise"
        except RuntimeError as e:
            assert "permission denied" in str(e)
    assert fake_ctx.get_market_snapshot.call_count == 3   # FUTU_RETRY_COUNT


def test_client_call_handles_3_value_return():
    """get_short_interest / get_daily_short_volume 返回 3 个值。"""
    from futu_ingest.client import FutuClient
    fake_ctx = MagicMock()
    fake_df = MagicMock()
    fake_secondary = MagicMock()
    fake_ctx.get_short_interest.return_value = (0, fake_df, fake_secondary)
    c = FutuClient()
    c._ctx = fake_ctx
    c._limiter_for = MagicMock()   # 跳过真实限频 sleep
    data = c.call("get_short_interest", "US.AAPL")
    assert data is fake_df


def test_limiter_for_uses_per_method_interval():
    """不同 method 拿到各自 interval；未列接口走默认。"""
    from futu_ingest.client import FutuClient
    from config import FUTU_DEFAULT_INTERVAL
    c = FutuClient()
    fast = c._limiter_for("get_company_operational_efficiency")  # 120-cap
    slow = c._limiter_for("get_company_profile")                 # 默认
    assert fast.delay == 0.312
    assert slow.delay == FUTU_DEFAULT_INTERVAL


def test_limiter_for_caches_same_instance():
    """同 method 多次取返回同一 limiter（共享窗口）。"""
    from futu_ingest.client import FutuClient
    c = FutuClient()
    assert c._limiter_for("get_market_snapshot") is c._limiter_for("get_market_snapshot")


def test_client_call_3_value_retries_on_error():
    """3值返回 + ret != RET_OK 也应正确重试。"""
    from futu_ingest.client import FutuClient
    fake_ctx = MagicMock()
    fake_ctx.get_short_interest.return_value = (-1, "no permission", None)
    c = FutuClient()
    c._ctx = fake_ctx
    c._limiter_for = MagicMock()   # 跳过真实限频 sleep
    with patch("futu_ingest.client.time.sleep"):
        try:
            c.call("get_short_interest", "US.AAPL")
            assert False, "should raise"
        except RuntimeError as e:
            assert "no permission" in str(e)
    assert fake_ctx.get_short_interest.call_count == 3  # FUTU_RETRY_COUNT
