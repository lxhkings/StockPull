import os
from unittest.mock import patch

def test_db_dict_is_assembled_from_env():
    """config.DB reads from environment via dotenv."""
    from config import DB
    assert DB["host"] == os.environ["DB_HOST"]
    assert DB["port"] == int(os.environ["DB_PORT"])
    assert DB["user"] == os.environ["DB_USER"]
    assert DB["password"] == os.environ["DB_PASSWORD"]
    assert DB["database"] == os.environ["DB_NAME"]
    assert DB["charset"] == "utf8mb4"
    assert DB["autocommit"] is False


def test_history_years_defaults_per_market():
    from config import HISTORY_YEARS_US, HISTORY_YEARS_CN, HISTORY_YEARS_HK, START_DATE_CN
    assert HISTORY_YEARS_US == 5
    assert HISTORY_YEARS_CN == 15
    assert HISTORY_YEARS_HK == 15
    assert START_DATE_CN == "2010-01-01"


def test_indices_metadata():
    from config import INDEX_CONFIG
    assert "SP500" in INDEX_CONFIG
    assert "CSI800" in INDEX_CONFIG
    assert "HSI" in INDEX_CONFIG
    assert INDEX_CONFIG["CSI800"]["etf"] == "510800"
    assert INDEX_CONFIG["HSI"]["etf"] == "2800.HK"
