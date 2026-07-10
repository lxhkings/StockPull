from unittest.mock import patch

import pytest


def test_succeeds_first_attempt_no_sleep():
    from retry_utils import retry_with_backoff
    calls = []
    def fn():
        calls.append(1)
        return "ok"
    with patch("retry_utils.time.sleep") as mock_sleep:
        result = retry_with_backoff(fn, retry_count=3, base_delay=5)
    assert result == "ok"
    assert len(calls) == 1
    mock_sleep.assert_not_called()


def test_retries_then_succeeds_with_exponential_backoff():
    from retry_utils import retry_with_backoff
    attempts = {"n": 0}
    def fn():
        attempts["n"] += 1
        if attempts["n"] < 2:
            raise ConnectionError("boom")
        return "ok"
    with patch("retry_utils.time.sleep") as mock_sleep:
        result = retry_with_backoff(fn, retry_count=3, base_delay=5, multiplier=3)
    assert result == "ok"
    assert attempts["n"] == 2
    mock_sleep.assert_called_once_with(5)  # 5 * 3**0


def test_exhausts_and_raises_last_exception_no_sleep_after_final():
    from retry_utils import retry_with_backoff
    err1 = ConnectionError("first")
    err2 = TimeoutError("second")
    calls = iter([err1, err2])
    def fn():
        raise next(calls)
    with patch("retry_utils.time.sleep") as mock_sleep:
        with pytest.raises(TimeoutError) as exc_info:
            retry_with_backoff(fn, retry_count=2, base_delay=5)
    assert exc_info.value is err2
    mock_sleep.assert_called_once_with(5)  # 只在第1次失败后sleep，最后一次失败直接抛


def test_should_retry_false_raises_immediately_without_retry():
    from retry_utils import retry_with_backoff
    calls = []
    def fn():
        calls.append(1)
        raise RuntimeError("permanent: 不支持")
    with patch("retry_utils.time.sleep") as mock_sleep:
        with pytest.raises(RuntimeError, match="permanent"):
            retry_with_backoff(
                fn, retry_count=5, base_delay=5,
                should_retry=lambda e: "不支持" not in str(e),
            )
    assert len(calls) == 1  # 永久错误：只调用1次，不重试
    mock_sleep.assert_not_called()


def test_context_included_in_warning_log(caplog):
    from retry_utils import retry_with_backoff
    import logging
    caplog.set_level(logging.WARNING, logger="retry_utils")
    def fn():
        raise ConnectionError("boom")
    with patch("retry_utils.time.sleep"):
        with pytest.raises(ConnectionError):
            retry_with_backoff(fn, retry_count=2, base_delay=1, context="myapi.call")
    assert any("myapi.call" in r.message for r in caplog.records)
