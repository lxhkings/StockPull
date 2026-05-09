import subprocess
import sys


def _run(*args):
    return subprocess.run(
        [sys.executable, "main.py", *args],
        capture_output=True, text=True
    )


def test_help_shows_subcommands():
    out = _run("--help")
    assert out.returncode == 0
    for sub in ("init", "daily", "rebase", "status"):
        assert sub in out.stdout


def test_unknown_subcommand_errors():
    out = _run("nonexistent")
    assert out.returncode != 0


def test_daily_market_choice_validated():
    out = _run("daily", "--market", "europe")
    assert out.returncode != 0
    assert "europe" in out.stderr or "europe" in out.stdout
