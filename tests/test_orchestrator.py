from unittest.mock import patch

from ts_ingest.orchestrator import run_full_backfill


def test_start_passed_through_to_valuation_backfill():
    with patch("ts_ingest.orchestrator.get_client"), \
         patch("ts_ingest.orchestrator.budget.precheck", return_value=[]), \
         patch("ts_ingest.orchestrator.val_backfill_all", return_value={"rows": 0}) as val:
        run_full_backfill(scope="valuation", start="20200101")
    val.assert_called_once_with(start="20200101")


def test_no_start_defaults_to_none_for_valuation_backfill():
    with patch("ts_ingest.orchestrator.get_client"), \
         patch("ts_ingest.orchestrator.budget.precheck", return_value=[]), \
         patch("ts_ingest.orchestrator.val_backfill_all", return_value={"rows": 0}) as val:
        run_full_backfill(scope="valuation")
    val.assert_called_once_with(start=None)


def test_start_passed_through_to_financial_backfill():
    with patch("ts_ingest.orchestrator.get_client"), \
         patch("ts_ingest.orchestrator.budget.precheck", return_value=[]), \
         patch("ts_ingest.orchestrator.fin_backfill_all", return_value={"rows": 0}) as fin:
        run_full_backfill(scope="financial", start="20200101")
    fin.assert_called_once_with(start="20200101")


def test_no_start_uses_financial_backfill_default():
    with patch("ts_ingest.orchestrator.get_client"), \
         patch("ts_ingest.orchestrator.budget.precheck", return_value=[]), \
         patch("ts_ingest.orchestrator.fin_backfill_all", return_value={"rows": 0}) as fin:
        run_full_backfill(scope="financial")
    fin.assert_called_once_with()


def test_lists_scope_calls_stock_dates_backfill():
    with patch("ts_ingest.orchestrator.get_client"), \
         patch("ts_ingest.orchestrator.budget.precheck", return_value=[]), \
         patch("ts_ingest.orchestrator.backfill_stocks_a", return_value={}), \
         patch("ts_ingest.orchestrator.backfill_stocks_hk", return_value={}), \
         patch("ts_ingest.orchestrator.backfill_stocks_us", return_value={}), \
         patch("ts_ingest.orchestrator.backfill_etf_basic", return_value={}), \
         patch("ts_ingest.orchestrator.backfill_hk_connect", return_value={}), \
         patch("ts_ingest.orchestrator.backfill_stock_dates",
               return_value={"listed": {}, "delisted": {}}) as dates:
        rep = run_full_backfill(scope="lists")
    dates.assert_called_once()
    assert "stock_dates" in rep.phases["lists"]
