"""Contract tests for shared CN equity batch runner."""
from datetime import date
from unittest.mock import MagicMock, patch

import pandas as pd


def test_normalize_pro_bar_shape():
    from apis.tushare.prices_cn_batch import normalize_pro_bar

    df = pd.DataFrame({
        "trade_date": ["20260511"],
        "open": [100.0], "high": [105.0], "low": [99.0],
        "close": [103.0], "vol": [1_000_000],
    })
    out = normalize_pro_bar(df)
    assert list(out.columns) == ["date", "open", "high", "low", "close", "volume"]
    assert out["date"].iloc[0] == date(2026, 5, 11)


def test_run_empty_tickers():
    from apis.tushare.prices_cn_batch import CnPriceSpec, run_cn_equity_batch

    spec = CnPriceSpec(
        label="cn", freq="D", data_type="price", price_table="prices",
    )
    assert run_cn_equity_batch([], spec=spec) == {}


def test_run_weekly_flush_uses_prices_weekly_and_on_duplicate():
    """Weekly path must flush prices_weekly with on_duplicate=True."""
    from apis.tushare.prices_cn_batch import CnPriceSpec, run_cn_equity_batch

    spec = CnPriceSpec(
        label="cn weekly",
        freq="W",
        data_type="price_weekly",
        price_table="prices_weekly",
        on_duplicate=True,
    )
    flush_calls = []

    def capture_flush(conn, prices_buf, sync_buf, *, spec):
        flush_calls.append({
            "price_table": spec.price_table,
            "on_duplicate": spec.on_duplicate,
            "sync_rows": list(sync_buf),
            "price_rows": list(prices_buf),
        })

    with patch("apis.tushare.prices_cn_batch.last_cn_trading_date",
               return_value=date(2026, 5, 16)), \
         patch("apis.tushare.prices_cn_batch.get_conn", return_value=MagicMock()), \
         patch("apis.tushare.prices_cn_batch.get_last_sync_map",
               return_value={"600519.SH": None}), \
         patch("apis.tushare.prices_cn_batch._fetch_one", return_value=pd.DataFrame({
             "date": [date(2026, 5, 16)],
             "open": [100.0], "high": [105.0], "low": [99.0],
             "close": [103.0], "volume": [1_000_000],
         })), \
         patch("apis.tushare.prices_cn_batch._flush_batch", side_effect=capture_flush):
        result = run_cn_equity_batch(["600519.SH"], spec=spec)

    assert result["600519.SH"] == "ok"
    assert flush_calls
    last = flush_calls[-1]
    assert last["price_table"] == "prices_weekly"
    assert last["on_duplicate"] is True
    assert last["sync_rows"][0][1] == "price_weekly"


def test_incremental_uses_last_map_not_per_ticker_get_last_sync():
    """Pending ticker start date must come from preloaded last_map."""
    from apis.tushare.prices_cn_batch import CnPriceSpec, run_cn_equity_batch

    spec = CnPriceSpec(
        label="cn", freq="D", data_type="price", price_table="prices",
    )
    last_sync = date(2026, 5, 10)

    with patch("apis.tushare.prices_cn_batch.last_cn_trading_date",
               return_value=date(2026, 5, 16)), \
         patch("apis.tushare.prices_cn_batch.get_conn", return_value=MagicMock()), \
         patch("apis.tushare.prices_cn_batch.get_last_sync_map",
               return_value={"600519.SH": last_sync}) as mock_map, \
         patch("apis.tushare.prices_cn_batch._fetch_one", return_value=pd.DataFrame({
             "date": [date(2026, 5, 16)],
             "open": [1.0], "high": [2.0], "low": [0.5],
             "close": [1.5], "volume": [100],
         })) as mock_fetch, \
         patch("apis.tushare.prices_cn_batch._flush_batch"):
        result = run_cn_equity_batch(["600519.SH"], spec=spec)

    assert result["600519.SH"] == "ok"
    mock_map.assert_called_once()
    start_arg = mock_fetch.call_args[0][1]
    assert start_arg == "20260511"  # last_sync + 1 day
    # freq passed through
    assert mock_fetch.call_args[0][3] == "D"
