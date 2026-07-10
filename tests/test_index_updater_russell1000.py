"""data/index_updater_russell1000.py 测试。

数据源：SEC EDGAR NPORT-P（IWB 持仓）+ company_tickers_exchange.json（名称→ticker）。
"""
from unittest.mock import patch, MagicMock
from datetime import date, datetime, timedelta
import json
import pandas as pd

from data.index_updater_russell1000 import (
    _normalize_name,
    _valid_us_ticker,
    _build_name_ticker_lookup,
    _find_iwb_accession,
    _parse_nport_holdings,
    fetch_russell1000_data,
    update_russell1000,
)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# _normalize_name
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_normalize_name_strips_suffix_and_punctuation():
    assert _normalize_name("Apple Inc.") == "APPLE"
    assert _normalize_name("Charles Schwab Corp") == "CHARLES SCHWAB"


def test_normalize_name_strips_leading_the():
    assert _normalize_name("The Coca-Cola Co") == "COCA COLA"


def test_normalize_name_strips_sec_state_suffix():
    assert _normalize_name("Foo Bar /DE/") == "FOO BAR"


def test_normalize_name_hyphen_between_letters_becomes_space():
    assert _normalize_name("TAKE-TWO INTERACTIVE") == "TAKE TWO INTERACTIVE"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# _valid_us_ticker
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_valid_us_ticker_accepts_normal_tickers():
    assert _valid_us_ticker("AAPL")
    assert _valid_us_ticker("BRK-B")


def test_valid_us_ticker_rejects_empty_and_too_long():
    assert not _valid_us_ticker("")
    assert not _valid_us_ticker("TOOLONGTICKER")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# _build_name_ticker_lookup
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@patch("data.index_updater_russell1000.fetch_with_retry")
def test_build_name_ticker_lookup_prefers_higher_priority_exchange(mock_fetch):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "fields": ["ticker", "name", "exchange"],
        "data": [
            ["AAPL", "Apple Inc.", "OTC"],
            ["AAPL", "Apple Inc.", "Nasdaq"],  # 同名不同 exchange，优先 Nasdaq
        ],
    }
    mock_fetch.return_value = mock_resp

    lookup = _build_name_ticker_lookup()

    assert lookup["APPLE"] == "AAPL"
    mock_fetch.assert_called_once()
    assert mock_fetch.call_args.kwargs["context"] == "russell1000.name_ticker_lookup"


@patch("data.index_updater_russell1000.fetch_with_retry")
def test_build_name_ticker_lookup_skips_invalid_ticker(mock_fetch):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "fields": ["ticker", "name", "exchange"],
        "data": [
            ["", "No Ticker Co", "Nasdaq"],
            ["TOOLONGTICKER", "Bad Ticker Co", "Nasdaq"],
        ],
    }
    mock_fetch.return_value = mock_resp

    lookup = _build_name_ticker_lookup()

    assert "NO TICKER CO" not in lookup
    assert "BAD TICKER CO" not in lookup


@patch("data.index_updater_russell1000.fetch_with_retry")
def test_build_name_ticker_lookup_applies_name_overrides(mock_fetch):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"fields": ["ticker", "name", "exchange"], "data": []}
    mock_fetch.return_value = mock_resp

    lookup = _build_name_ticker_lookup()

    # NAME_OVERRIDES 里的硬编码覆盖应始终存在
    assert lookup["D R HORTON"] == "DHI"
    assert lookup["ELI LILLY"] == "LLY"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# _find_iwb_accession
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_find_iwb_accession_uses_valid_cache(tmp_path):
    cache_file = tmp_path / "iwb_accession.json"
    cache_file.write_text(json.dumps({
        "accession": "0001-cached",
        "cached_at": datetime.now().isoformat(),
    }))
    with patch("data.index_updater_russell1000._CACHE_FILE", cache_file), \
         patch("data.index_updater_russell1000.fetch_with_retry") as mock_fetch:
        acc = _find_iwb_accession()
    assert acc == "0001-cached"
    mock_fetch.assert_not_called()


def test_find_iwb_accession_ignores_expired_cache(tmp_path):
    cache_file = tmp_path / "iwb_accession.json"
    cache_file.write_text(json.dumps({
        "accession": "0001-stale",
        "cached_at": (datetime.now() - timedelta(days=31)).isoformat(),
    }))
    submissions_resp = MagicMock()
    submissions_resp.json.return_value = {
        "filings": {"recent": {
            "form": ["NPORT-P"],
            "filingDate": ["2026-06-01"],
            "accessionNumber": ["0001-fresh"],
        }}
    }
    doc_resp = MagicMock()
    doc_resp.status_code = 200
    doc_resp.text = "<seriesName>iShares Russell 1000 ETF</seriesName>"

    with patch("data.index_updater_russell1000._CACHE_FILE", cache_file), \
         patch("data.index_updater_russell1000.fetch_with_retry", return_value=submissions_resp), \
         patch("data.index_updater_russell1000.requests.get", return_value=doc_resp), \
         patch("data.index_updater_russell1000.time.sleep"):
        acc = _find_iwb_accession()

    assert acc == "0001-fresh"
    assert cache_file.read_text()  # 重新写入缓存
    assert json.loads(cache_file.read_text())["accession"] == "0001-fresh"


def test_find_iwb_accession_skips_non_matching_series(tmp_path):
    cache_file = tmp_path / "iwb_accession.json"  # 不存在 → 无缓存
    submissions_resp = MagicMock()
    submissions_resp.json.return_value = {
        "filings": {"recent": {
            "form": ["NPORT-P", "NPORT-P"],
            "filingDate": ["2026-06-01", "2026-05-01"],
            "accessionNumber": ["0001-other", "0002-iwb"],
        }}
    }
    other_resp = MagicMock(status_code=200, text="<seriesName>iShares Some Other ETF</seriesName>")
    iwb_resp = MagicMock(status_code=200, text="<seriesName>iShares Russell 1000 ETF</seriesName>")

    with patch("data.index_updater_russell1000._CACHE_FILE", cache_file), \
         patch("data.index_updater_russell1000.fetch_with_retry", return_value=submissions_resp), \
         patch("data.index_updater_russell1000.requests.get", side_effect=[other_resp, iwb_resp]), \
         patch("data.index_updater_russell1000.time.sleep"):
        acc = _find_iwb_accession()

    assert acc == "0002-iwb"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# _parse_nport_holdings
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_parse_nport_holdings_matches_equity_by_name():
    xml = """
    <invstOrSec><assetCat>EC</assetCat><name>Apple Inc.</name></invstOrSec>
    <invstOrSec><assetCat>EQ</assetCat><name>Charles Schwab Corp</name></invstOrSec>
    """
    lookup = {"APPLE": "AAPL", "CHARLES SCHWAB": "SCHW"}
    df = _parse_nport_holdings(xml, lookup)
    assert set(df["ticker"]) == {"AAPL", "SCHW"}


def test_parse_nport_holdings_skips_non_equity_assets():
    xml = """
    <invstOrSec><assetCat>DBT</assetCat><name>Some Bond Co</name></invstOrSec>
    """
    lookup = {"SOME BOND CO": "BOND"}
    df = _parse_nport_holdings(xml, lookup)
    assert df.empty


def test_parse_nport_holdings_skips_unmatched_names():
    xml = """
    <invstOrSec><assetCat>EC</assetCat><name>Unknown Foreign Co</name></invstOrSec>
    """
    df = _parse_nport_holdings(xml, {})
    assert df.empty
    assert list(df.columns) == ["ticker", "name", "sector"]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# fetch_russell1000_data（编排）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@patch("data.index_updater_russell1000.time.sleep")
@patch("data.index_updater_russell1000.fetch_with_retry")
@patch("data.index_updater_russell1000._find_iwb_accession", return_value="0001-acc")
@patch("data.index_updater_russell1000._build_name_ticker_lookup", return_value={"APPLE": "AAPL"})
def test_fetch_russell1000_data_orchestrates_lookup_accession_and_parse(
    mock_lookup, mock_acc, mock_fetch, mock_sleep,
):
    xml_resp = MagicMock()
    xml_resp.text = "<invstOrSec><assetCat>EC</assetCat><name>Apple Inc.</name></invstOrSec>"
    mock_fetch.return_value = xml_resp

    df = fetch_russell1000_data()

    assert list(df["ticker"]) == ["AAPL"]
    mock_lookup.assert_called_once()
    mock_acc.assert_called_once()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# update_russell1000
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@patch("data.index_updater_russell1000.get_conn")
def test_update_russell1000_skips_when_already_updated_today(mock_get_conn):
    with patch("data.index_updater_russell1000.get_last_snapshot_date", return_value=date.today()), \
         patch("data.index_updater_russell1000.fetch_russell1000_data") as mock_fetch:
        result = update_russell1000()
    assert result == (0, 0)
    mock_fetch.assert_not_called()


@patch("data.index_updater_russell1000.get_conn")
def test_update_russell1000_skips_when_fetch_returns_empty(mock_get_conn):
    conn = MagicMock()
    mock_get_conn.return_value = conn
    with patch("data.index_updater_russell1000.get_last_snapshot_date", return_value=None), \
         patch("data.index_updater_russell1000.fetch_russell1000_data", return_value=pd.DataFrame(columns=["ticker", "name", "sector"])):
        result = update_russell1000()
    assert result == (0, 0)


@patch("data.index_updater_russell1000.register_stocks")
@patch("data.index_updater_russell1000.get_conn")
def test_update_russell1000_inserts_constituents_and_registers_stocks(mock_get_conn, mock_register):
    conn = MagicMock()
    cur = MagicMock()
    cur.executemany.return_value = 2
    conn.cursor.return_value.__enter__.return_value = cur
    mock_get_conn.return_value = conn

    df = pd.DataFrame({
        "ticker": ["AAPL", "SCHW"],
        "name": ["Apple Inc.", "Charles Schwab Corp"],
        "sector": [None, None],
    })
    with patch("data.index_updater_russell1000.get_last_snapshot_date", return_value=None), \
         patch("data.index_updater_russell1000.fetch_russell1000_data", return_value=df):
        inserted, count = update_russell1000()

    assert (inserted, count) == (2, 2)
    mock_register.assert_called_once()
    conn.commit.assert_called_once()
    assert conn.close.call_count == 2  # 一次 get_last_snapshot_date 检查 + 一次写入
