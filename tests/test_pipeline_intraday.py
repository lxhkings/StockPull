"""Tests for Pipeline.daily() Step 5 intraday integration."""
from jobs.pipeline import Pipeline


class _USModule:
    """Mock US market module with intraday support."""
    market_id = "us"
    def update_index(self): return ([], 0, 0)
    def list_active_tickers(self, index=None): return []
    def backfill_new(self, new_tickers): return {}
    def incremental(self, tickers): return {}
    def update_index_price(self): return 0
    def intraday(self): return {}


class _CNModule:
    """Mock CN market module without intraday support."""
    market_id = "cn"
    def update_index(self): return ([], 0, 0)
    def list_active_tickers(self, index=None): return []
    def backfill_new(self, new_tickers): return {}
    def incremental(self, tickers): return {}
    def update_index_price(self): return 0


def test_pipeline_daily_calls_intraday_when_available():
    from unittest.mock import MagicMock
    mod = _USModule()
    mod.intraday = MagicMock(return_value={})
    Pipeline(mod).daily()
    mod.intraday.assert_called_once_with()


def test_pipeline_daily_skips_intraday_when_not_available():
    """CN module has no intraday — must not raise AttributeError."""
    Pipeline(_CNModule()).daily()  # no exception = pass