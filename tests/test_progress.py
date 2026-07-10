import logging


def test_format_duration_under_minute():
    from core.progress import format_duration
    assert format_duration(45) == "45s"


def test_format_duration_with_minutes():
    from core.progress import format_duration
    assert format_duration(125) == "2m05s"


def test_log_progress_emits_on_every_n(caplog):
    from core.progress import log_progress
    caplog.set_level(logging.INFO, logger="core.progress")
    log_progress(50, 200, t0=0.0, every=50, context="[cn] ")
    assert any("[cn] 50/200 (25%)" in r.message for r in caplog.records)


def test_log_progress_silent_between_intervals(caplog):
    from core.progress import log_progress
    caplog.set_level(logging.INFO, logger="core.progress")
    log_progress(37, 200, t0=0.0, every=50, context="[cn] ")
    assert len(caplog.records) == 0


def test_log_progress_always_emits_at_total(caplog):
    from core.progress import log_progress
    caplog.set_level(logging.INFO, logger="core.progress")
    log_progress(199, 200, t0=0.0, every=50, context="[cn] ")
    assert len(caplog.records) == 0
    log_progress(200, 200, t0=0.0, every=50, context="[cn] ")
    assert any("200/200 (100%)" in r.message for r in caplog.records)


def test_log_progress_every_1_always_emits(caplog):
    from core.progress import log_progress
    caplog.set_level(logging.INFO, logger="core.progress")
    log_progress(3, 200, t0=0.0, every=1, context="[cn] ")
    assert any("3/200" in r.message for r in caplog.records)


def test_log_progress_includes_extra_suffix(caplog):
    from core.progress import log_progress
    caplog.set_level(logging.INFO, logger="core.progress")
    log_progress(50, 100, t0=0.0, every=50, context="tushare_x: ", extra="ok=48 skip=1 err=1")
    assert any("ok=48 skip=1 err=1" in r.message for r in caplog.records)
