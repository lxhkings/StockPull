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
    calls = []
    def fake_backfill(client, t):
        calls.append(t)
        return 3
    rows, ok = ticker_stream(fake_backfill, client=object(), tickers=["A", "B"], label="x")
    assert (rows, ok) == (6, 2)
    assert calls == ["A", "B"]


def test_ticker_stream_swallows_per_ticker_error():
    def fake_backfill(client, t):
        if t == "B":
            raise ValueError("boom")
        return 1
    rows, ok = ticker_stream(fake_backfill, client=object(), tickers=["A", "B", "C"], label="x")
    assert (rows, ok) == (2, 2)   # B 异常被吞，A/C 仍计
