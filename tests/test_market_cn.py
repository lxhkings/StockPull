"""Tests for CN market module."""
from unittest.mock import patch


@patch("jobs.market_cn.backfill_stocks_a")
@patch("jobs.market_cn.list_active_tickers")
def test_update_index_returns_set_diff(mock_list, mock_backfill):
    """prev/curr ticker sets → added list + removed count; inserted from backfill."""
    from jobs.market_cn import update_index

    mock_list.side_effect = [
        ["600519.SH", "000001.SZ"],           # prev
        ["600519.SH", "000001.SZ", "300750.SZ"],  # curr: +300750
    ]
    mock_backfill.return_value = 1

    new_tickers, inserted, removed = update_index()

    mock_backfill.assert_called_once()
    assert mock_list.call_count == 2
    assert new_tickers == ["300750.SZ"]
    assert inserted == 1
    assert removed == 0


@patch("jobs.market_cn.backfill_stocks_a")
@patch("jobs.market_cn.list_active_tickers")
def test_update_index_removed_count(mock_list, mock_backfill):
    from jobs.market_cn import update_index

    mock_list.side_effect = [
        ["600519.SH", "000001.SZ"],
        ["600519.SH"],  # 000001 gone
    ]
    mock_backfill.return_value = 0

    new_tickers, inserted, removed = update_index()
    assert new_tickers == []
    assert inserted == 0
    assert removed == 1


@patch("jobs.market_cn.backfill_stocks_a")
@patch("jobs.market_cn.list_active_tickers")
def test_update_index_no_change(mock_list, mock_backfill):
    from jobs.market_cn import update_index

    mock_list.side_effect = [
        ["600519.SH"],
        ["600519.SH"],
    ]
    mock_backfill.return_value = 0
    new_tickers, inserted, removed = update_index()
    assert new_tickers == []
    assert removed == 0


@patch("jobs.market_cn.query")
def test_list_active_tickers(mock_query):
    """list_active_tickers should return tickers from stocks table."""
    from jobs.market_cn import list_active_tickers

    mock_query.return_value = [
        {"ticker": "600519.SH"},
        {"ticker": "000001.SZ"},
        {"ticker": "300750.SZ"},
    ]

    tickers = list_active_tickers()

    assert tickers == ["600519.SH", "000001.SZ", "300750.SZ"]
    mock_query.assert_called_once()


def test_intraday_is_noop():
    from jobs.market_cn import intraday
    assert intraday() == {}
    assert intraday(["1h"], full_rebase=True) == {}


@patch("apis.tushare.etf_cn.update_etf_prices", return_value=42)
def test_rebase_etf_delegates(mock_upd):
    from jobs.market_cn import rebase_etf
    assert rebase_etf(full_rebase=True) == 42
    mock_upd.assert_called_once_with(full_rebase=True)
