"""Budget: 进程级调用计数与权限预检。"""
from unittest.mock import MagicMock


def setup_function():
    from ts_ingest import budget
    budget.reset()


def test_tick_increments_total_and_per_api():
    from ts_ingest import budget
    budget.tick("stock_basic")
    budget.tick("stock_basic")
    budget.tick("pro_bar")
    snap = budget.snapshot()
    assert snap["total"] == 3
    assert snap["per_api"]["stock_basic"] == 2
    assert snap["per_api"]["pro_bar"] == 1


def test_report_includes_elapsed_and_rate():
    from ts_ingest import budget
    budget.tick("a")
    rep = budget.report()
    assert "calls=" in rep
    assert "elapsed=" in rep


def test_precheck_passes_when_sample_call_returns_data():
    from ts_ingest import budget
    fake_client = MagicMock()
    fake_df = MagicMock()
    fake_df.empty = False
    fake_client.call.return_value = fake_df
    failed = budget.precheck(fake_client, ["stock_basic"])
    assert failed == []


def test_precheck_returns_failed_apis():
    from ts_ingest import budget
    fake_client = MagicMock()
    fake_df = MagicMock()
    fake_df.empty = False
    fake_client.call.side_effect = [
        fake_df,
        Exception("权限不足"),
    ]
    failed = budget.precheck(fake_client, ["stock_basic", "income_vip"])
    assert failed == ["income_vip"]
