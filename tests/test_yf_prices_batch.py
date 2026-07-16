"""Contract tests for shared US equity batch runner."""
from datetime import date
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest


def test_price_rows_from_df_shape():
    from apis.yfinance.prices_batch import price_rows_from_df

    df = pd.DataFrame({
        "ticker": ["AAPL"],
        "date": [date(2026, 7, 10)],
        "open": [1.0], "high": [2.0], "low": [0.5],
        "close": [1.5], "volume": [100],
    })
    rows = price_rows_from_df(df)
    assert rows == [("AAPL", date(2026, 7, 10), 1.0, 2.0, 0.5, 1.5, 100)]


def test_run_weekly_flush_uses_prices_weekly_and_ignore():
    """Weekly path must batch-flush prices_weekly with INSERT IGNORE semantics."""
    from apis.yfinance.prices_batch import UsPriceSpec, run_us_equity_batch

    target = date(2026, 5, 11)
    spec = UsPriceSpec(
        label="weekly batch",
        interval="1wk",
        data_type="price_weekly",
        price_table="prices_weekly",
        probe=lambda d: "ok",
        target_date=lambda: target,
        end_exclusive=lambda d: d + __import__("datetime").timedelta(days=7),
        on_duplicate=False,
        support_years=False,
    )

    # Minimal multi-index download frame for one ticker
    idx = pd.DatetimeIndex([pd.Timestamp("2026-05-11")])
    cols = pd.MultiIndex.from_product(
        [["AAPL"], ["Open", "High", "Low", "Close", "Volume"]]
    )
    raw = pd.DataFrame(
        [[180.0, 182.0, 178.0, 181.0, 1_000_000]],
        index=idx, columns=cols,
    )

    mock_conn = MagicMock()
    flush_calls = []

    def capture_flush(conn, price_rows, sync_rows, *, on_duplicate=True, price_table="prices"):
        flush_calls.append({
            "price_rows": price_rows,
            "sync_rows": sync_rows,
            "on_duplicate": on_duplicate,
            "price_table": price_table,
        })

    with patch("apis.yfinance.prices_batch.get_conn", return_value=mock_conn), \
         patch("apis.yfinance.prices_batch.download_with_retry", return_value=raw), \
         patch("apis.yfinance.prices_batch.get_last_sync_map", return_value={"AAPL": None}), \
         patch("apis.yfinance.prices_batch.flush_prices_and_sync", side_effect=capture_flush), \
         patch("apis.yfinance.prices_batch.YF_BATCH_SIZE", 40):
        result = run_us_equity_batch(["AAPL"], spec=spec, full_rebase=True)

    assert result["AAPL"] == "ok"
    assert len(flush_calls) == 1
    assert flush_calls[0]["price_table"] == "prices_weekly"
    assert flush_calls[0]["on_duplicate"] is False
    assert flush_calls[0]["sync_rows"][0][1] == "price_weekly"


def test_run_empty_tickers():
    from apis.yfinance.prices_batch import UsPriceSpec, run_us_equity_batch
    from datetime import date as d

    spec = UsPriceSpec(
        label="batch", interval="1d", data_type="price", price_table="prices",
        probe=lambda x: "ok", target_date=lambda: d(2026, 7, 10),
        end_exclusive=lambda x: x, on_duplicate=False, support_years=True,
    )
    assert run_us_equity_batch([], spec=spec) == {}


def test_probe_rate_limit_skips_without_download():
    from apis.yfinance.prices_batch import UsPriceSpec, run_us_equity_batch
    from datetime import date as d

    called = {"dl": False}

    def boom_dl(*a, **k):
        called["dl"] = True
        raise AssertionError("should not download")

    spec = UsPriceSpec(
        label="batch", interval="1d", data_type="price", price_table="prices",
        probe=lambda x: "rate_limit", target_date=lambda: d(2026, 7, 10),
        end_exclusive=lambda x: x, on_duplicate=False, support_years=True,
    )
    with patch("apis.yfinance.prices_batch.download_with_retry", side_effect=boom_dl):
        result = run_us_equity_batch(["AAPL"], spec=spec)
    assert result == {"AAPL": "error: rate_limit"}
    assert called["dl"] is False
