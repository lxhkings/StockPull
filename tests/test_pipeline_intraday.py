"""Tests for Pipeline.daily() — intraday is CLI-only, not part of daily."""
from unittest.mock import MagicMock

from jobs.pipeline import Pipeline


def _full_mod(**overrides):
    mod = MagicMock()
    mod.market_id = "us"
    mod.update_index.return_value = ([], 0, 0)
    mod.list_active_tickers.return_value = []
    mod.incremental.return_value = {}
    mod.update_index_price.return_value = 0
    mod.intraday.return_value = {}
    for k, v in overrides.items():
        setattr(mod, k, v)
    return mod


def test_pipeline_daily_does_not_call_intraday():
    mod = _full_mod()
    Pipeline(mod).daily()
    mod.intraday.assert_not_called()


def test_pipeline_daily_cn_still_completes_without_intraday():
    mod = _full_mod(market_id="cn")
    Pipeline(mod).daily()
    mod.update_index_price.assert_called_once()
    mod.intraday.assert_not_called()
