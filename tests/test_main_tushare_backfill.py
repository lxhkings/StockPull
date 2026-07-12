"""Tests for main.py cmd_tushare_backfill / cmd_tushare_flush local-buffer flow."""

from unittest.mock import MagicMock, patch

from main import cmd_tushare_backfill, cmd_tushare_flush, cmd_tushare_full, cmd_tushare_sync
from main import main as main_cli


def _fake_report():
    rep = MagicMock()
    rep.render.return_value = "fake report"
    return rep


def test_backfill_uses_local_buffer_and_flushes():
    with patch("core.db_client.set_local_first") as set_local, \
         patch("apis.tushare.orchestrator.run_full_backfill", return_value=_fake_report()) as run, \
         patch("core.local_buffer.flush", return_value={"replayed": 5, "remaining": 0}) as flush:
        rc = cmd_tushare_backfill(scope="valuation", market="cn", dry_run=False, start="20100101")

    assert rc == 0
    run.assert_called_once_with(scope="valuation", market="cn", dry_run=False, start="20100101")
    # 打开本地优先模式（带 tushare 自己的 buffer_path），跑完必须关闭
    assert set_local.call_args_list[0].args[0] is True
    assert set_local.call_args_list[-1].args == (False,)
    flush.assert_called_once()


def test_backfill_dry_run_skips_local_buffer():
    with patch("core.db_client.set_local_first") as set_local, \
         patch("apis.tushare.orchestrator.run_full_backfill", return_value=_fake_report()) as run:
        rc = cmd_tushare_backfill(scope="all", market="all", dry_run=True)

    assert rc == 0
    run.assert_called_once_with(scope="all", market="all", dry_run=True, start=None)
    set_local.assert_not_called()


def test_backfill_flush_failure_keeps_buffer_and_returns_1():
    with patch("core.db_client.set_local_first"), \
         patch("apis.tushare.orchestrator.run_full_backfill", return_value=_fake_report()), \
         patch("core.local_buffer.flush", side_effect=RuntimeError("NAS down")), \
         patch("core.local_buffer.pending_count", return_value=42):
        rc = cmd_tushare_backfill(scope="financial", market="cn", dry_run=False)

    assert rc == 1


def test_tushare_flush_no_pending():
    with patch("core.local_buffer.pending_count", return_value=0), \
         patch("core.local_buffer.flush") as flush:
        rc = cmd_tushare_flush()

    assert rc == 0
    flush.assert_not_called()


def test_tushare_flush_replays_pending():
    with patch("core.local_buffer.pending_count", return_value=10), \
         patch("core.local_buffer.flush", return_value={"replayed": 10, "remaining": 0}) as flush:
        rc = cmd_tushare_flush()

    assert rc == 0
    flush.assert_called_once()


def test_tushare_full_forces_start_from_backfill_start():
    with patch("main.cmd_tushare_backfill", return_value=0) as backfill:
        rc = cmd_tushare_full(scope="all", market="cn", dry_run=False)

    assert rc == 0
    backfill.assert_called_once_with("all", "cn", False, start="20100101")


def test_tushare_sync_passes_no_start():
    with patch("main.cmd_tushare_backfill", return_value=0) as backfill:
        rc = cmd_tushare_sync(scope="valuation", market="cn", dry_run=False)

    assert rc == 0
    backfill.assert_called_once_with("valuation", "cn", False, start=None)


def test_tushare_full_cli_dispatch():
    with patch("main.cmd_tushare_full", return_value=0) as full:
        rc = main_cli(["tushare", "full", "--scope", "valuation", "--market", "cn"])

    assert rc == 0
    full.assert_called_once_with("valuation", "cn", False)


def test_tushare_sync_cli_dispatch():
    # 新路径 tushare sync → cmd_tushare_backfill(..., start=None)
    with patch("main.cmd_tushare_backfill", return_value=0) as backfill:
        rc = main_cli(["tushare", "sync", "--scope", "shareholder_return"])

    assert rc == 0
    backfill.assert_called_once_with("shareholder_return", "all", False, None)
