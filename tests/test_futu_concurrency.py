import threading
import time

from futu_ingest.concurrency import run_streams, ticker_stream


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
    with patch("futu_ingest.concurrency.fresh_tickers", return_value=set()), \
         patch("futu_ingest.concurrency.mark_ok"):
        rows, ok, skipped = ticker_stream(fake_backfill, client=object(), tickers=["A", "B"], data_type="us_x")
    assert (rows, ok, skipped) == (6, 2, 0)
    assert calls == ["A", "B"]


def test_ticker_stream_swallows_per_ticker_error():
    from unittest.mock import patch
    def fake_backfill(client, t):
        if t == "B":
            raise ValueError("boom")
        return 1
    with patch("futu_ingest.concurrency.fresh_tickers", return_value=set()), \
         patch("futu_ingest.concurrency.mark_ok"), \
         patch("futu_ingest.concurrency.mark_error"):
        rows, ok, skipped = ticker_stream(fake_backfill, client=object(), tickers=["A", "B", "C"], data_type="us_x")
    assert (rows, ok, skipped) == (2, 2, 0)   # B 异常被吞，A/C 仍计


def test_ticker_stream_skips_fresh_and_marks_pulled():
    from unittest.mock import MagicMock, patch

    client = MagicMock()
    fn = MagicMock(return_value=3)
    with patch("futu_ingest.concurrency.fresh_tickers", return_value={"AAPL"}), \
         patch("futu_ingest.concurrency.mark_ok") as mok, \
         patch("futu_ingest.concurrency.FUTU_REFRESH_DAYS", {"us_x": 80}):
        rows, ok, skipped = ticker_stream(fn, client, ["AAPL", "MSFT"], "us_x")
    # AAPL fresh -> skipped, fn 只对 MSFT 调一次
    fn.assert_called_once_with(client, "MSFT")
    assert (rows, ok, skipped) == (3, 1, 1)
    mok.assert_called_once_with("MSFT", "us_x", 3)


def test_ticker_stream_force_ignores_freshness():
    from unittest.mock import MagicMock, patch

    client = MagicMock()
    fn = MagicMock(return_value=1)
    with patch("futu_ingest.concurrency.fresh_tickers") as ft, \
         patch("futu_ingest.concurrency.mark_ok"), \
         patch("futu_ingest.concurrency.FUTU_REFRESH_DAYS", {"us_x": 80}):
        rows, ok, skipped = ticker_stream(fn, client, ["AAPL", "MSFT"], "us_x", force=True)
    ft.assert_not_called()
    assert fn.call_count == 2
    assert (rows, ok, skipped) == (2, 2, 0)


def test_ticker_stream_marks_error_on_exception():
    from unittest.mock import MagicMock, patch

    client = MagicMock()
    fn = MagicMock(side_effect=RuntimeError("boom"))
    with patch("futu_ingest.concurrency.fresh_tickers", return_value=set()), \
         patch("futu_ingest.concurrency.mark_error") as merr, \
         patch("futu_ingest.concurrency.FUTU_REFRESH_DAYS", {"us_x": 80}):
        rows, ok, skipped = ticker_stream(fn, client, ["AAPL"], "us_x")
    assert (rows, ok, skipped) == (0, 0, 0)
    merr.assert_called_once_with("AAPL", "us_x", "boom")
