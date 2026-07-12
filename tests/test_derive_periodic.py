from unittest.mock import patch, MagicMock
import pandas as pd
from datetime import date

from apis.tushare.derive_periodic import derive_for_ticker


def test_derive_for_ticker_writes_both_tables():
    daily = pd.DataFrame({
        "date":   [date(2024, 1, 2), date(2024, 1, 3)],
        "open":   [10.0, 11.0],
        "high":   [11.0, 12.0],
        "low":    [9.5, 10.5],
        "close":  [10.5, 11.5],
        "volume": [100, 200],
    })
    with patch("apis.tushare.derive_periodic._read_daily", return_value=daily), \
         patch("apis.tushare.derive_periodic.get_conn") as mock_conn:
        cur = MagicMock()
        mock_conn.return_value.__enter__ = lambda s: mock_conn.return_value
        mock_conn.return_value.cursor.return_value.__enter__ = lambda s: cur
        n = derive_for_ticker("600519.SH")
    assert n["weekly"] >= 1
    assert n["monthly"] >= 1
    assert cur.executemany.call_count == 2
