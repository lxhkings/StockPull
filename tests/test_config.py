import os

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


def test_cn_sector_etfs_covers_gics_11():
    """CN_SECTOR_ETFS must cover all 11 GICS sectors plus themes."""
    from config import CN_SECTOR_ETFS

    assert len(CN_SECTOR_ETFS) >= 11, "must cover at least 11 sectors"

    # Every entry has name + gics fields
    for ts_code, meta in CN_SECTOR_ETFS.items():
        assert "." in ts_code and ts_code.endswith((".SH", ".SZ")), f"bad ts_code {ts_code}"
        assert "name" in meta and meta["name"], f"missing name for {ts_code}"
        assert "gics" in meta and meta["gics"], f"missing gics for {ts_code}"

    # GICS 11 sectors all present
    gics_values = {meta["gics"] for meta in CN_SECTOR_ETFS.values()}
    required_gics = {
        "Energy", "Materials", "Industrials",
        "ConsumerDiscretionary", "ConsumerStaples", "HealthCare",
        "Financials", "InformationTechnology", "CommunicationServices",
        "Utilities", "RealEstate",
    }
    missing = required_gics - gics_values
    assert not missing, f"missing GICS sectors: {missing}"
