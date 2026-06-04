from unittest.mock import patch

from futu_ingest.orchestrator import run_sync, list_us_tickers


def test_run_backfill_includes_profile_phase():
    with patch("futu_ingest.orchestrator.list_us_tickers", return_value=["AAPL"]), \
         patch("futu_ingest.orchestrator.profile_backfill_all") as mock_profile, \
         patch("futu_ingest.orchestrator.fin_backfill_all"), \
         patch("futu_ingest.orchestrator.earnings_backfill_all"), \
         patch("futu_ingest.orchestrator.actions_backfill_all"):
        mock_profile.return_value = {"rows": 18, "tickers": 1}
        rep = run_sync(scope="profile", force=True)
    assert "profile" in rep
    assert rep["profile"]["rows"] == 18


def test_run_weekly_executes_3_snapshots():
    with patch("futu_ingest.orchestrator.list_us_tickers", return_value=["AAPL"]), \
         patch("futu_ingest.orchestrator.snapshot_run_weekly") as mock_weekly:
        mock_weekly.return_value = {"valuation": 1, "rating": 5, "morningstar": 1, "tickers": 1}
        rep = run_sync(scope="weekly", force=False)
    assert rep["weekly"]["valuation"] == 1
    assert rep["weekly"]["rating"] == 5


def test_run_daily_includes_batch2():
    with patch("futu_ingest.orchestrator.list_us_tickers", return_value=["AAPL"]), \
         patch("futu_ingest.orchestrator.snapshot_run_daily") as mock_daily, \
         patch("futu_ingest.orchestrator.daily_ext_run") as mock_ext:
        mock_daily.return_value = {"shares": 1029, "analyst": 1029, "tickers": 1029}
        mock_ext.return_value = {"capital_flow": 250, "capital_dist": 1029,
                                 "short_interest": 100, "short_volume": 100, "tickers": 1029}
        rep = run_sync(scope="daily", force=False)
    assert "daily_ext" in rep
    assert rep["daily_ext"]["capital_flow"] == 250
