"""Tests for Pipeline.daily() Step 5 intraday (always called)."""
from unittest.mock import MagicMock

from jobs.pipeline import Pipeline


def _full_mod(**overrides):
    mod = MagicMock()
    mod.market_id = "us"
    mod.update_index.return_value = ([], 0, 0)
    mod.list_active_tickers.return_value = []
    mod.backfill_new.return_value = {}
    mod.incremental.return_value = {}
    mod.update_index_price.return_value = 0
    mod.intraday.return_value = {}
    for k, v in overrides.items():
        setattr(mod, k, v)
    return mod


def test_pipeline_daily_always_calls_intraday():
    mod = _full_mod()
    Pipeline(mod).daily()
    mod.intraday.assert_called_once_with()


def test_pipeline_daily_cn_intraday_noop_ok():
    """CN-style module with no-op intraday must not raise."""
    mod = _full_mod(market_id="cn")
    Pipeline(mod).daily()
    mod.intraday.assert_called_once_with()
