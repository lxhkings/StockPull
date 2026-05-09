from unittest.mock import MagicMock, call


def test_pipeline_runs_steps_in_order():
    """Pipeline calls update_index → backfill_new → incremental → update_index_price."""
    from data.pipeline import Pipeline

    market_module = MagicMock()
    market_module.market_id = "us"
    market_module.update_index.return_value = (["NEW1", "NEW2"], 5, 1)  # (new_added_tickers, total_inserted, removed)
    market_module.list_active_tickers.return_value = ["AAPL", "MSFT", "NEW1", "NEW2"]
    market_module.backfill_new.return_value = {"NEW1": "ok", "NEW2": "ok"}
    market_module.incremental.return_value = {"AAPL": "ok", "MSFT": "ok", "NEW1": "ok", "NEW2": "ok"}
    market_module.update_index_price.return_value = 1

    p = Pipeline(market_module)
    p.daily()

    market_module.update_index.assert_called_once()
    market_module.backfill_new.assert_called_once_with(["NEW1", "NEW2"])
    market_module.incremental.assert_called_once_with(["AAPL", "MSFT", "NEW1", "NEW2"])
    market_module.update_index_price.assert_called_once()


def test_pipeline_skips_backfill_when_no_new():
    from data.pipeline import Pipeline

    market_module = MagicMock()
    market_module.market_id = "cn"
    market_module.update_index.return_value = ([], 0, 0)
    market_module.list_active_tickers.return_value = ["600519.SH"]
    market_module.incremental.return_value = {"600519.SH": "ok"}
    market_module.update_index_price.return_value = 1

    Pipeline(market_module).daily()

    market_module.backfill_new.assert_not_called()
    market_module.incremental.assert_called_once()
