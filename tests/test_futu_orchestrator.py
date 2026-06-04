from unittest.mock import patch

import futu_ingest.orchestrator as orch
from futu_ingest.orchestrator import run_sync, list_us_tickers


def test_run_backfill_financial_scope_calls_only_financial():
    with patch("futu_ingest.orchestrator.list_us_tickers", return_value=["AAPL"]), \
         patch("futu_ingest.orchestrator.fin_backfill_all", return_value={"rows": 4}) as fin, \
         patch("futu_ingest.orchestrator.earnings_backfill_all") as earn, \
         patch("futu_ingest.orchestrator.actions_backfill_all") as act:
        rep = run_sync(scope="financial", force=True)
    fin.assert_called_once()
    earn.assert_not_called()
    act.assert_not_called()
    assert "financial" in rep


def test_run_backfill_all_calls_financial_earnings_actions():
    with patch("futu_ingest.orchestrator.list_us_tickers", return_value=["AAPL"]), \
         patch("futu_ingest.orchestrator.fin_backfill_all", return_value={}) as fin, \
         patch("futu_ingest.orchestrator.earnings_backfill_all", return_value={}) as earn, \
         patch("futu_ingest.orchestrator.actions_backfill_all", return_value={}) as act, \
         patch("futu_ingest.orchestrator.profile_backfill_all", return_value={}), \
         patch("futu_ingest.orchestrator.revenue_backfill_all", return_value={}), \
         patch("futu_ingest.orchestrator.shareholders_backfill_all", return_value={}), \
         patch("futu_ingest.orchestrator.efficiency_backfill_all", return_value={}), \
         patch("futu_ingest.orchestrator.snapshot_run_daily", return_value={}), \
         patch("futu_ingest.orchestrator.daily_ext_run", return_value={}), \
         patch("futu_ingest.orchestrator.snapshot_run_weekly", return_value={}):
        run_sync(scope="all", force=True)
    fin.assert_called_once()
    earn.assert_called_once()
    act.assert_called_once()


def test_run_sync_all_calls_every_group_with_force():
    with patch.object(orch, "list_us_tickers", return_value=["AAPL"]), \
         patch.object(orch, "fin_backfill_all", return_value={"rows": 1}) as fin, \
         patch.object(orch, "earnings_backfill_all", return_value={"earnings_rows": 1}) as ear, \
         patch.object(orch, "actions_backfill_all", return_value={"dividends": 1}) as act, \
         patch.object(orch, "profile_backfill_all", return_value={"rows": 1}) as pro, \
         patch.object(orch, "revenue_backfill_all", return_value={"revenue_rows": 1}) as rev, \
         patch.object(orch, "shareholders_backfill_all", return_value={"tickers": 1}) as sh, \
         patch.object(orch, "efficiency_backfill_all", return_value={"rows": 1}) as eff, \
         patch.object(orch, "snapshot_run_daily", return_value={"shares": 1}) as sd, \
         patch.object(orch, "daily_ext_run", return_value={"capital_flow": 1}) as de, \
         patch.object(orch, "snapshot_run_weekly", return_value={"valuation": 1}) as sw:
        rep = orch.run_sync(scope="all", force=True)
    for m in (fin, ear, act, pro, rev, sh, eff):
        m.assert_called_once_with(["AAPL"], force=True)
    sd.assert_called_once_with(["AAPL"], force=True)
    de.assert_called_once_with(["AAPL"], force=True)
    sw.assert_called_once_with(["AAPL"], force=True)
    assert rep["scope"] == "all" and rep["force"] is True


def test_run_sync_scope_daily_only_runs_daily_groups():
    with patch.object(orch, "list_us_tickers", return_value=["AAPL"]), \
         patch.object(orch, "fin_backfill_all") as fin, \
         patch.object(orch, "snapshot_run_daily", return_value={"shares": 1}) as sd, \
         patch.object(orch, "daily_ext_run", return_value={"capital_flow": 1}) as de, \
         patch.object(orch, "snapshot_run_weekly") as sw:
        rep = orch.run_sync(scope="daily", force=False)
    fin.assert_not_called()
    sw.assert_not_called()
    sd.assert_called_once_with(["AAPL"], force=False)
    de.assert_called_once_with(["AAPL"], force=False)
    assert "daily" in rep
