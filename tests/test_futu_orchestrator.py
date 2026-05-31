from unittest.mock import patch

from futu_ingest.orchestrator import run_backfill, list_us_tickers


def test_run_backfill_financial_scope_calls_only_financial():
    with patch("futu_ingest.orchestrator.list_us_tickers", return_value=["AAPL"]), \
         patch("futu_ingest.orchestrator.fin_backfill_all", return_value={"rows": 4}) as fin, \
         patch("futu_ingest.orchestrator.earnings_backfill_all") as earn, \
         patch("futu_ingest.orchestrator.actions_backfill_all") as act:
        rep = run_backfill(scope="financial")
    fin.assert_called_once()
    earn.assert_not_called()
    act.assert_not_called()
    assert "financial" in rep


def test_run_backfill_all_calls_financial_earnings_actions():
    with patch("futu_ingest.orchestrator.list_us_tickers", return_value=["AAPL"]), \
         patch("futu_ingest.orchestrator.fin_backfill_all", return_value={}) as fin, \
         patch("futu_ingest.orchestrator.earnings_backfill_all", return_value={}) as earn, \
         patch("futu_ingest.orchestrator.actions_backfill_all", return_value={}) as act:
        run_backfill(scope="all")
    fin.assert_called_once()
    earn.assert_called_once()
    act.assert_called_once()
