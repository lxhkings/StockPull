"""rebase --etf-only triggers full ETF re-pull without touching stocks."""
from unittest.mock import patch


@patch("apis.tushare.etf_cn.update_etf_prices")
def test_rebase_etf_only_calls_update_with_full_rebase(mock_update):
    """main.py prices rebase --market cn --etf-only → update_etf_prices(full_rebase=True)."""
    mock_update.return_value = 100

    from main import main
    rc = main(["prices", "rebase", "--market", "cn", "--etf-only"])

    assert rc == 0
    mock_update.assert_called_once_with(full_rebase=True)
