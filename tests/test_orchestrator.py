from unittest.mock import patch

from apis.tushare.orchestrator import run_full_backfill


def test_start_passed_through_to_valuation_backfill():
    with patch("apis.tushare.orchestrator.get_client"), \
         patch("apis.tushare.orchestrator.budget.precheck", return_value=[]), \
         patch("apis.tushare.orchestrator.val_backfill_all", return_value={"rows": 0}) as val:
        run_full_backfill(scope="valuation", start="20200101")
    val.assert_called_once_with(start="20200101")


def test_no_start_defaults_to_none_for_valuation_backfill():
    with patch("apis.tushare.orchestrator.get_client"), \
         patch("apis.tushare.orchestrator.budget.precheck", return_value=[]), \
         patch("apis.tushare.orchestrator.val_backfill_all", return_value={"rows": 0}) as val:
        run_full_backfill(scope="valuation")
    val.assert_called_once_with(start=None)


def test_start_passed_through_to_financial_backfill():
    with patch("apis.tushare.orchestrator.get_client"), \
         patch("apis.tushare.orchestrator.budget.precheck", return_value=[]), \
         patch("apis.tushare.orchestrator.fin_backfill_all", return_value={"rows": 0}) as fin:
        run_full_backfill(scope="financial", start="20200101")
    fin.assert_called_once_with(start="20200101")


def test_no_start_uses_financial_backfill_default():
    with patch("apis.tushare.orchestrator.get_client"), \
         patch("apis.tushare.orchestrator.budget.precheck", return_value=[]), \
         patch("apis.tushare.orchestrator.fin_backfill_all", return_value={"rows": 0}) as fin:
        run_full_backfill(scope="financial")
    fin.assert_called_once_with()


def test_lists_scope_calls_stock_dates_backfill():
    with patch("apis.tushare.orchestrator.get_client"), \
         patch("apis.tushare.orchestrator.budget.precheck", return_value=[]), \
         patch("apis.tushare.orchestrator.backfill_stocks_a", return_value={}), \
         patch("apis.tushare.orchestrator.backfill_stocks_hk", return_value={}), \
         patch("apis.tushare.orchestrator.backfill_stocks_us", return_value={}), \
         patch("apis.tushare.orchestrator.backfill_etf_basic", return_value={}), \
         patch("apis.tushare.orchestrator.backfill_hk_connect", return_value={}), \
         patch("apis.tushare.orchestrator.backfill_stock_dates",
               return_value={"listed": {}, "delisted": {}}) as dates:
        rep = run_full_backfill(scope="lists")
    dates.assert_called_once()
    assert "stock_dates" in rep.phases["lists"]


def test_shareholder_return_scope_calls_backfill_all():
    with patch("apis.tushare.orchestrator.get_client"), \
         patch("apis.tushare.orchestrator.budget.precheck", return_value=[]), \
         patch("apis.tushare.orchestrator.sr_backfill_all", return_value={"rows": 0}) as sr:
        run_full_backfill(scope="shareholder_return", start="20200101")
    sr.assert_called_once_with(start="20200101")


def test_shareholder_return_scope_no_start_passes_none():
    with patch("apis.tushare.orchestrator.get_client"), \
         patch("apis.tushare.orchestrator.budget.precheck", return_value=[]), \
         patch("apis.tushare.orchestrator.sr_backfill_all", return_value={"rows": 0}) as sr:
        run_full_backfill(scope="shareholder_return")
    sr.assert_called_once_with(start=None)
