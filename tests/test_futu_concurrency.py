import time

import pytest

from apis.futu.concurrency import batch_with_bisect, run_streams, ticker_stream


def test_run_streams_aggregates_by_key():
    out = run_streams([
        ("a", lambda: (10, 2)),
        ("b", lambda: (5, 1)),
    ])
    assert out == {"a": (10, 2), "b": (5, 1)}


def test_run_streams_runs_concurrently():
    """两个 stream 各睡 0.2s，并发总耗时应远小于 0.4s。"""
    def slow():
        time.sleep(0.2)
        return (1, 1)
    t0 = time.monotonic()
    run_streams([("a", slow), ("b", slow)])
    assert time.monotonic() - t0 < 0.35


def test_ticker_stream_sums_rows_and_ok():
    from unittest.mock import patch
    calls = []
    def fake_backfill(client, t):
        calls.append(t)
        return 3
    with patch("apis.futu.concurrency.fresh_tickers", return_value=set()), \
         patch("apis.futu.concurrency.mark_ok"):
        rows, ok, skipped = ticker_stream(fake_backfill, client=object(), tickers=["A", "B"], data_type="us_x")
    assert (rows, ok, skipped) == (6, 2, 0)
    assert calls == ["A", "B"]


def test_ticker_stream_swallows_per_ticker_error():
    from unittest.mock import patch
    def fake_backfill(client, t):
        if t == "B":
            raise ValueError("boom")
        return 1
    with patch("apis.futu.concurrency.fresh_tickers", return_value=set()), \
         patch("apis.futu.concurrency.mark_ok"), \
         patch("apis.futu.concurrency.mark_error"):
        rows, ok, skipped = ticker_stream(fake_backfill, client=object(), tickers=["A", "B", "C"], data_type="us_x")
    assert (rows, ok, skipped) == (2, 2, 0)   # B 异常被吞，A/C 仍计


def test_ticker_stream_skips_fresh_and_marks_pulled():
    from unittest.mock import MagicMock, patch

    client = MagicMock()
    fn = MagicMock(return_value=3)
    with patch("apis.futu.concurrency.fresh_tickers", return_value={"AAPL"}), \
         patch("apis.futu.concurrency.mark_ok") as mok, \
         patch("apis.futu.concurrency.FUTU_REFRESH_DAYS", {"us_x": 80}):
        rows, ok, skipped = ticker_stream(fn, client, ["AAPL", "MSFT"], "us_x")
    # AAPL fresh -> skipped, fn 只对 MSFT 调一次
    fn.assert_called_once_with(client, "MSFT")
    assert (rows, ok, skipped) == (3, 1, 1)
    mok.assert_called_once_with("MSFT", "us_x", 3)


def test_ticker_stream_force_ignores_freshness():
    from unittest.mock import MagicMock, patch

    client = MagicMock()
    fn = MagicMock(return_value=1)
    with patch("apis.futu.concurrency.fresh_tickers") as ft, \
         patch("apis.futu.concurrency.mark_ok"), \
         patch("apis.futu.concurrency.FUTU_REFRESH_DAYS", {"us_x": 80}):
        rows, ok, skipped = ticker_stream(fn, client, ["AAPL", "MSFT"], "us_x", force=True)
    ft.assert_not_called()
    assert fn.call_count == 2
    assert (rows, ok, skipped) == (2, 2, 0)


def _bisect_client(bad: set[str]):
    """模拟 client：批含 bad code 即抛'未知股票'，否则返回该批 code 列表。"""
    from unittest.mock import MagicMock

    client = MagicMock()

    def call(method, codes, *a, **k):
        hit = next((c for c in codes if c in bad), None)
        if hit is not None:
            raise RuntimeError(f"futu.{method} ret=-1: 未知股票 {hit}")
        return list(codes)

    client.call.side_effect = call
    return client


def test_batch_with_bisect_all_good_single_call():
    client = _bisect_client(bad=set())
    out = batch_with_bisect(client, "get_market_snapshot", ["A", "B", "C"])
    assert out == [["A", "B", "C"]]          # 一次成功，未二分
    assert client.call.call_count == 1


def test_batch_with_bisect_isolates_unknown_ticker():
    client = _bisect_client(bad={"B"})
    out = batch_with_bisect(client, "get_market_snapshot", ["A", "B", "C", "D"])
    # B 被隔离跳过，好 code 全保留（顺序按二分拼接）
    survived = [c for batch in out for c in batch]
    assert sorted(survived) == ["A", "C", "D"]
    assert "B" not in survived


def test_batch_with_bisect_reraises_other_errors():
    from unittest.mock import MagicMock
    client = MagicMock()
    client.call.side_effect = RuntimeError("futu.x ret=-1: 限频")
    with pytest.raises(RuntimeError, match="限频"):
        batch_with_bisect(client, "get_market_snapshot", ["A", "B"])


def test_ticker_stream_skips_permanent_error_not_retry():
    """永久错误(不支持/未知股票)标 skip(mark_skip)、计入 skipped，不进 error 重试。"""
    from unittest.mock import MagicMock, patch

    client = MagicMock()

    def fn(c, t):
        if t == "AMT":   # REIT，接口不支持
            raise RuntimeError("futu.x ret=-1: 只支持港股、美股正股，其他市场或股票类型不支持")
        return 2

    with patch("apis.futu.concurrency.fresh_tickers", return_value=set()), \
         patch("apis.futu.concurrency.mark_ok"), \
         patch("apis.futu.concurrency.mark_skip") as mskip, \
         patch("apis.futu.concurrency.mark_error") as merr, \
         patch("apis.futu.concurrency.FUTU_REFRESH_DAYS", {"us_x": 80}):
        rows, ok, skipped = ticker_stream(fn, client, ["AAPL", "AMT", "MSFT"], "us_x")
    assert (rows, ok, skipped) == (4, 2, 1)   # AMT 标 skip
    mskip.assert_called_once_with("AMT", "us_x")
    merr.assert_not_called()                  # 永久错误不记 error


def test_ticker_stream_marks_error_on_exception():
    from unittest.mock import MagicMock, patch

    client = MagicMock()
    fn = MagicMock(side_effect=RuntimeError("boom"))
    with patch("apis.futu.concurrency.fresh_tickers", return_value=set()), \
         patch("apis.futu.concurrency.mark_error") as merr, \
         patch("apis.futu.concurrency.FUTU_REFRESH_DAYS", {"us_x": 80}):
        rows, ok, skipped = ticker_stream(fn, client, ["AAPL"], "us_x")
    assert (rows, ok, skipped) == (0, 0, 0)
    merr.assert_called_once_with("AAPL", "us_x", "boom")
