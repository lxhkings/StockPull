from unittest.mock import patch

from main import main


def test_futu_full_dispatches_force_true():
    with patch("apis.futu.orchestrator.run_sync", return_value={"scope": "all"}) as rs:
        rc = main(["futu", "full", "--scope", "all"])
    assert rc == 0
    rs.assert_called_once_with(scope="all", force=True)


def test_futu_sync_dispatches_force_false():
    with patch("apis.futu.orchestrator.run_sync", return_value={"scope": "daily"}) as rs:
        rc = main(["futu", "sync", "--scope", "daily"])
    assert rc == 0
    rs.assert_called_once_with(scope="daily", force=False)


def test_futu_sync_default_scope_all():
    with patch("apis.futu.orchestrator.run_sync", return_value={"scope": "all"}) as rs:
        rc = main(["futu", "sync"])
    assert rc == 0
    rs.assert_called_once_with(scope="all", force=False)


def test_old_futu_full_still_dispatches_force_true(capsys):
    """旧顶层 futu-full 兼容：仍 force=True，并打 deprecation。"""
    with patch("apis.futu.orchestrator.run_sync", return_value={"scope": "all"}) as rs:
        rc = main(["futu-full", "--scope", "all"])
    assert rc == 0
    rs.assert_called_once_with(scope="all", force=True)
    err = capsys.readouterr().err
    assert "[deprecated]" in err
    assert "`futu-full`" in err
    assert "`futu full`" in err
