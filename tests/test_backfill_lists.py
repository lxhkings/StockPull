"""列表/成分回填：mock client + mock get_conn。"""
from unittest.mock import patch, MagicMock
import pandas as pd

from ts_ingest.backfill_lists import (
    backfill_stocks_a, backfill_etf_basic, backfill_hk_connect,
)


def _df(**cols) -> pd.DataFrame:
    return pd.DataFrame(cols)


def test_backfill_stocks_a_inserts_into_stocks():
    fake_client = MagicMock()
    fake_client.call.side_effect = [
        _df(ts_code=["600519.SH"], symbol=["600519"], name=["贵州茅台"], exchange=["SSE"]),
        _df(ts_code=["000001.SZ"], symbol=["000001"], name=["平安银行"], exchange=["SZSE"]),
    ]
    with patch("ts_ingest.backfill_lists.get_conn") as mock_conn, \
         patch("ts_ingest.backfill_lists.get_client", return_value=fake_client):
        cur = MagicMock()
        mock_conn.return_value.__enter__ = lambda s: s
        mock_conn.return_value.cursor.return_value.__enter__ = lambda s: cur
        n = backfill_stocks_a()
    assert n == 2
    args = cur.executemany.call_args
    sql = args[0][0]
    assert "ON DUPLICATE KEY UPDATE" in sql


def test_backfill_etf_basic_uses_two_markets():
    fake_client = MagicMock()
    fake_client.call.side_effect = [
        _df(ts_code=["510300.SH"], name=["华泰柏瑞沪深300ETF"]),
        _df(ts_code=["110011.OF"], name=["易方达货币"]),
    ]
    with patch("ts_ingest.backfill_lists.get_conn") as mock_conn, \
         patch("ts_ingest.backfill_lists.get_client", return_value=fake_client):
        cur = MagicMock()
        mock_conn.return_value.cursor.return_value.__enter__ = lambda s: cur
        n = backfill_etf_basic()
    assert fake_client.call.call_count == 2
    fake_client.call.assert_any_call("fund_basic", market="E")
    fake_client.call.assert_any_call("fund_basic", market="O")
    assert n >= 1


def test_backfill_hk_connect_writes_both_directions():
    fake_client = MagicMock()
    fake_client.call.side_effect = [
        _df(ts_code=["600519.SH"], name=["贵州茅台"]),
        _df(ts_code=["000001.SZ"], name=["平安银行"]),
    ]
    with patch("ts_ingest.backfill_lists.get_conn") as mock_conn, \
         patch("ts_ingest.backfill_lists.get_client", return_value=fake_client):
        cur = MagicMock()
        mock_conn.return_value.cursor.return_value.__enter__ = lambda s: cur
        backfill_hk_connect()
    fake_client.call.assert_any_call("hs_const", hs_type="SH")
    fake_client.call.assert_any_call("hs_const", hs_type="SZ")
