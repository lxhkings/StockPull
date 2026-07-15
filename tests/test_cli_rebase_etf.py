"""rebase --etf-only goes through market_cn, not apis.tushare directly."""
from unittest.mock import patch


@patch("jobs.market_cn.rebase_etf", return_value=100)
def test_rebase_etf_only_calls_market_cn(mock_rebase):
    from main import main
    rc = main(["prices", "rebase", "--market", "cn", "--etf-only"])
    assert rc == 0
    mock_rebase.assert_called_once_with(full_rebase=True)


def test_rebase_etf_only_rejects_non_cn():
    from main import main
    rc = main(["prices", "rebase", "--market", "us", "--etf-only"])
    assert rc == 1
