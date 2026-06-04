from unittest.mock import patch

from main import main


def test_futu_full_dispatches_force_true():
    with patch("futu_ingest.orchestrator.run_sync", return_value={"scope": "all"}) as rs:
        rc = main(["futu-full", "--scope", "all"])
    assert rc == 0
    rs.assert_called_once_with(scope="all", force=True)


def test_futu_sync_dispatches_force_false():
    with patch("futu_ingest.orchestrator.run_sync", return_value={"scope": "daily"}) as rs:
        rc = main(["futu-sync", "--scope", "daily"])
    assert rc == 0
    rs.assert_called_once_with(scope="daily", force=False)


def test_futu_sync_default_scope_all():
    with patch("futu_ingest.orchestrator.run_sync", return_value={"scope": "all"}) as rs:
        rc = main(["futu-sync"])
    assert rc == 0
    rs.assert_called_once_with(scope="all", force=False)