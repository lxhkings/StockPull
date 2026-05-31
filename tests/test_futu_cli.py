from unittest.mock import patch

from main import main


def test_futu_backfill_dispatches():
    with patch("futu_ingest.orchestrator.run_backfill", return_value={"scope": "all"}) as rb:
        rc = main(["futu-backfill", "--scope", "all"])
    assert rc == 0
    rb.assert_called_once_with(scope="all")


def test_futu_daily_dispatches():
    with patch("futu_ingest.orchestrator.run_daily", return_value={"shares": 1}) as rd:
        rc = main(["futu-daily"])
    assert rc == 0
    rd.assert_called_once()
