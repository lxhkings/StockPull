import subprocess
import sys
from unittest.mock import patch

from main import main


def _run(*args):
    return subprocess.run(
        [sys.executable, "main.py", *args],
        capture_output=True, text=True
    )


def test_help_shows_subcommands():
    out = _run("--help")
    assert out.returncode == 0
    for sub in ("prices", "tushare", "futu", "init", "status", "db"):
        assert sub in out.stdout
    # 旧顶层 help=SUPPRESS，一级列表不展示
    assert "tushare-sync" not in out.stdout
    assert "migrate-intraday" not in out.stdout


def test_prices_daily_help():
    out = _run("prices", "daily", "--help")
    assert out.returncode == 0
    assert "--market" in out.stdout


def test_tushare_sync_help_has_scope():
    out = _run("tushare", "sync", "--help")
    assert out.returncode == 0
    assert "--scope" in out.stdout


def test_prices_without_subcommand_errors():
    out = _run("prices")
    assert out.returncode != 0


def test_unknown_subcommand_errors():
    out = _run("nonexistent")
    assert out.returncode != 0


def test_daily_market_choice_validated():
    # 旧入口仍可解析参数校验
    out = _run("daily", "--market", "europe")
    assert out.returncode != 0
    assert "europe" in out.stderr or "europe" in out.stdout


def test_old_daily_help_still_works():
    out = _run("daily", "--help")
    assert out.returncode == 0


def test_old_daily_emits_deprecation_on_run(capsys):
    with patch("main.cmd_daily", return_value=0) as daily:
        rc = main(["daily", "--market", "us"])
    assert rc == 0
    daily.assert_called_once()
    err = capsys.readouterr().err
    assert "[deprecated]" in err
    assert "`daily`" in err
    assert "`prices daily`" in err


def test_old_tushare_sync_emits_deprecation_on_run(capsys):
    with patch("main.cmd_tushare_sync", return_value=0) as sync:
        rc = main(["tushare-sync", "--scope", "lists"])
    assert rc == 0
    sync.assert_called_once()
    err = capsys.readouterr().err
    assert "[deprecated]" in err
    assert "`tushare-sync`" in err
    assert "`tushare sync`" in err


def test_new_prices_daily_no_deprecation(capsys):
    with patch("main.cmd_daily", return_value=0):
        rc = main(["prices", "daily", "--market", "us"])
    assert rc == 0
    err = capsys.readouterr().err
    assert "[deprecated]" not in err


def test_new_tushare_sync_no_deprecation(capsys):
    with patch("main.cmd_tushare_backfill", return_value=0):
        rc = main(["tushare", "sync", "--scope", "lists"])
    assert rc == 0
    err = capsys.readouterr().err
    assert "[deprecated]" not in err
