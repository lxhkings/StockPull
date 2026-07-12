from unittest.mock import MagicMock


def test_pipeline_runs_steps_in_order():
    """Pipeline: update_index → incremental → update_index_price (no intraday)."""
    from jobs.pipeline import Pipeline

    market_module = MagicMock()
    market_module.market_id = "us"
    market_module.update_index.return_value = (["NEW1", "NEW2"], 5, 1)
    market_module.list_active_tickers.return_value = ["AAPL", "MSFT", "NEW1", "NEW2"]
    market_module.incremental.return_value = {
        "AAPL": "ok", "MSFT": "ok", "NEW1": "ok", "NEW2": "ok",
    }
    market_module.update_index_price.return_value = 1
    market_module.intraday.return_value = {}

    p = Pipeline(market_module)
    p.daily()

    market_module.update_index.assert_called_once()
    market_module.incremental.assert_called_once_with(["AAPL", "MSFT", "NEW1", "NEW2"])
    market_module.update_index_price.assert_called_once()
    market_module.intraday.assert_not_called()


def test_pipeline_incremental_includes_all_even_when_new():
    """New tickers are covered by incremental only (no separate backfill step)."""
    from jobs.pipeline import Pipeline

    market_module = MagicMock()
    market_module.market_id = "us"
    market_module.update_index.return_value = (["NEW1"], 1, 0)
    market_module.list_active_tickers.return_value = ["AAPL", "NEW1"]
    market_module.incremental.return_value = {"AAPL": "ok", "NEW1": "ok"}
    market_module.update_index_price.return_value = 0
    market_module.intraday.return_value = {}

    Pipeline(market_module).daily()

    market_module.incremental.assert_called_once_with(["AAPL", "NEW1"])
    market_module.intraday.assert_not_called()


def test_pipeline_when_no_new_tickers():
    from jobs.pipeline import Pipeline

    market_module = MagicMock()
    market_module.market_id = "cn"
    market_module.update_index.return_value = ([], 0, 0)
    market_module.list_active_tickers.return_value = ["600519.SH"]
    market_module.incremental.return_value = {"600519.SH": "ok"}
    market_module.update_index_price.return_value = 1
    market_module.intraday.return_value = {}

    Pipeline(market_module).daily()

    market_module.incremental.assert_called_once()
    market_module.intraday.assert_not_called()
