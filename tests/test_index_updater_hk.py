# tests/test_index_updater_hk.py
from unittest.mock import patch, MagicMock
import pandas as pd
from io import StringIO


def _wiki_html_with_hsi_table():
    """Mock Wikipedia HTML with HSI constituents table."""
    html = """
    <html><body>
    <table>
      <tr><th>Code</th><th>Company</th></tr>
      <tr><td>00700</td><td>Tencent Holdings</td></tr>
      <tr><td>09988</td><td>Alibaba Group</td></tr>
      <tr><td>00005</td><td>HSBC Holdings</td></tr>
    </table>
    </body></html>
    """
    return html


@patch("data.index_updater_hk.requests.get")
def test_fetch_hsi_from_wikipedia(mock_get):
    """Test HSI fetch from Wikipedia."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = _wiki_html_with_hsi_table()
    mock_get.return_value = mock_resp

    from data.index_updater_hk import _fetch_hsi
    df = _fetch_hsi()

    assert df is not None
    assert len(df) == 3
    assert set(df["ticker"]) == {"00700.HK", "09988.HK", "00005.HK"}
    assert "name" in df.columns
    assert df[df["ticker"] == "00700.HK"]["name"].iloc[0] == "Tencent Holdings"


@patch("data.index_updater_hk.requests.get")
def test_fetch_hsi_handles_fetch_error(mock_get):
    """Test HSI fetch handles HTTP errors."""
    mock_resp = MagicMock()
    mock_resp.status_code = 404
    mock_get.return_value = mock_resp

    from data.index_updater_hk import _fetch_hsi
    df = _fetch_hsi()

    assert df is None