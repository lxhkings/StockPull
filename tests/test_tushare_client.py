"""Tushare SDK 包装：单例、限速、重试。"""
from unittest.mock import MagicMock, patch
import pandas as pd
import pytest


# Mock config before importing client
@pytest.fixture(autouse=True)
def mock_config():
    with patch.dict('os.environ', {'TUSHARE_TOKEN': 'fake_token'}):
        with patch('ts_ingest.client.TUSHARE_TOKEN', 'fake_token'):
            with patch('ts_ingest.client.TUSHARE_RATE_INTERVAL', 0.13):
                with patch('ts_ingest.client.TUSHARE_RETRY_COUNT', 3):
                    with patch('ts_ingest.client.TUSHARE_RETRY_DELAY', 5.0):
                        with patch('ts_ingest.client.RateLimiter'):
                            yield


def test_get_client_returns_singleton():
    with patch("ts_ingest.client.ts.pro_api") as mock_pro:
        mock_pro.return_value = MagicMock()
        # Need to clear the lru_cache
        from ts_ingest import client
        client.get_client.cache_clear()
        c1 = client.get_client()
        c2 = client.get_client()
    assert c1 is c2


def test_call_invokes_named_api():
    fake_pro = MagicMock()
    fake_pro.stock_basic.return_value = pd.DataFrame({"ts_code": ["600519.SH"]})
    with patch("ts_ingest.client.ts.pro_api", return_value=fake_pro):
        from ts_ingest import client
        client.get_client.cache_clear()
        client_obj = client.get_client()
        df = client_obj.call("stock_basic", exchange="SSE")
    fake_pro.stock_basic.assert_called_once_with(exchange="SSE")
    assert df.iloc[0]["ts_code"] == "600519.SH"


def test_call_retries_then_succeeds():
    fake_pro = MagicMock()
    fake_pro.stock_basic.side_effect = [
        Exception("transient 503"),
        pd.DataFrame({"ts_code": ["600519.SH"]}),
    ]
    with patch("ts_ingest.client.ts.pro_api", return_value=fake_pro), \
         patch("retry_utils.time.sleep"):
        from ts_ingest import client
        client.get_client.cache_clear()
        client_obj = client.get_client()
        df = client_obj.call("stock_basic", exchange="SSE")
    assert fake_pro.stock_basic.call_count == 2
    assert len(df) == 1


def test_call_raises_after_retry_exhaustion():
    fake_pro = MagicMock()
    fake_pro.stock_basic.side_effect = Exception("permanent failure")
    with patch("ts_ingest.client.ts.pro_api", return_value=fake_pro), \
         patch("retry_utils.time.sleep"):
        from ts_ingest import client
        client.get_client.cache_clear()
        client_obj = client.get_client()
        with pytest.raises(Exception, match="permanent failure"):
            client_obj.call("stock_basic")
    assert fake_pro.stock_basic.call_count == 3  # TUSHARE_RETRY_COUNT
