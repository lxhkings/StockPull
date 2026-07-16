"""Verify update_index_price() only runs sector ETF updater."""
from unittest.mock import patch


@patch("apis.tushare.etf_cn.update_etf_prices")
def test_update_index_price_calls_etf_updater_only(mock_etf_update):
    """CN index_prices path is sector ETFs only (no CSI800 / index_daily)."""
    mock_etf_update.return_value = 42

    from jobs.market_cn import update_index_price
    total = update_index_price()

    assert total == 42
    mock_etf_update.assert_called_once_with(full_rebase=False)
