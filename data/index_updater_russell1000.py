"""Russell 1000 成分股更新模块。

数据源：
1. SEC EDGAR NPORT-P（iShares Russell 1000 ETF = IWB 月度持仓申报）
   - 有 CUSIP + 公司名，无 ticker
2. SEC company_tickers_exchange.json（公司名 → ticker 映射）
   - 标准化名称匹配，覆盖率 ~96%
3. 硬编码覆盖表（处理名称格式差异无法自动匹配的少数公司）
"""

from __future__ import annotations

import html
import json
import logging
import os
import re
import time
import requests
import pandas as pd
from datetime import date, datetime, timedelta
from pathlib import Path

from db import get_conn
from data.index_base import register_stocks, get_last_snapshot_date

log = logging.getLogger(__name__)

ISHARES_TRUST_CIK = "1100663"
ISHARES_TRUST_CIK_PADDED = ISHARES_TRUST_CIK.zfill(10)
EDGAR_HEADERS = {"User-Agent": "StockPull research lxhkings@gmail.com"}
EDGAR_RATE_DELAY = 0.15  # SEC 限制 10 req/sec

_CACHE_FILE = Path(__file__).parent / ".cache" / "iwb_accession.json"
_CACHE_MAX_DAYS = 30  # accession 超过 30 天则重新扫描

# 标准化后名称 → ticker 的硬编码覆盖表（用于自动匹配失败的公司）
NAME_OVERRIDES: dict[str, str] = {
    "D R HORTON": "DHI",
    "CHARLES SCHWAB": "SCHW",
    "COMERICA": "CMA",
    "US BANCORP": "USB",
    "OREILLY AUTOMOTIVE": "ORLY",
    "ELI LILLY": "LLY",
    "VERTEX PHARMACEUTICALS": "VRTX",
    "BECTON DICKINSON": "BDX",
    "AO SMITH": "AOS",
    "JB HUNT TRANSPORT": "JBHT",
    "WR BERKLEY": "WRB",
    "AIR PRODUCTS CHEMICALS": "APD",
    "AIR LEASE": "AL",
    "CONFLUENT": "CFLT",
    "SEALED AIR": "SEE",
    "HOLOGIC": "HOLX",
    "T ROWE PRICE": "TROW",
    "EXACT SCIENCES": "EXAS",
    "RIVIAN AUTOMOTIVE": "RIVN",
    "MP MATERIALS": "MP",
    "SYNOVUS": "SNV",
    "UNIVERSAL DISPLAY": "OLED",
    "GAMING LEISURE PROPERTIES": "GLPI",
    "SLB": "SLB",
    "PURE STORAGE": "PSTG",
    "HONEYWELL": "HON",
    "FRONTIER COMMUNICATIONS PARENT": "FYBR",
    "DAYFORCE": "DAY",
    "FNB": "FNB",
    "CIVITAS RESOURCES": "CIVI",
    "ACUITY": "AYI",
    "MILLICOM": "TIGO",
}

# SEC 公司名后缀（标准化时移除）
_SUFFIXES = [
    "CORPORATION", "INCORPORATED", "COMPANY", "INC", "CORP", "CO",
    "LIMITED", "LTD", "LLC", "PLC", "SA", "AG", "NV", "SE", "LP", "REIT",
    "CLASS A", "CLASS B", "CLASS C", "CL A", "CL B", "CL C",
    "HOLDINGS", "GROUP", "INTERNATIONAL", "INTL", "INDUSTRIES", "INSURANCE",
    "TECHNOLOGIES", "TECHNOLOGY", "SOLUTIONS", "SERVICES", "SYSTEMS",
    "FINANCIAL", "ENTERPRISES", "PARTNERS", "BANCORPORATION", "BANCSHARES",
    "NATIONAL ASSOCIATION", "PUBLIC", "AND COMPANY",
]


def _normalize_name(name: str) -> str:
    """标准化公司名以便匹配：大写、移除后缀、移除标点。"""
    name = html.unescape(name).upper().strip()
    # 移除 SEC 状态后缀：/NY、/NY/、/DE/ 等
    name = re.sub(r"\s*/[A-Z0-9]+/?\s*$", "", name)
    name = re.sub(r"[.,&]", " ", name)
    # 复合词连字符转空格（TAKE-TWO → TAKE TWO）
    name = re.sub(r"(?<=[A-Z])-(?=[A-Z])", " ", name)
    name = re.sub(r"\s+", " ", name).strip()
    name = re.sub(r"^THE\s+", "", name)
    for suffix in _SUFFIXES:
        name = re.sub(r"\s+" + suffix + r"\s*$", "", name)
        name = re.sub(r"\b" + suffix + r"\b", " ", name)
    name = re.sub(r"[^A-Z0-9 ]", "", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name


def _valid_us_ticker(t: str) -> bool:
    return bool(t) and bool(re.match(r"^[A-Z0-9][A-Z0-9-]{0,5}$", t))


def _build_name_ticker_lookup() -> dict[str, str]:
    """从 SEC company_tickers_exchange.json 构建标准化名称 → ticker 查找表。"""
    resp = requests.get(
        "https://www.sec.gov/files/company_tickers_exchange.json",
        headers=EDGAR_HEADERS,
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    fields = data["fields"]
    name_idx = fields.index("name")
    ticker_idx = fields.index("ticker")
    exchange_idx = fields.index("exchange")

    exchange_priority = {"Nasdaq": 1, "NYSE": 2, "ARCA": 3, "NYSEARCA": 3, "BATS": 4, "OTC": 5}
    lookup: dict[str, tuple[str, int]] = {}
    for entry in data["data"]:
        ticker = entry[ticker_idx]
        name = entry[name_idx]
        if not ticker or not name or not _valid_us_ticker(ticker.upper()):
            continue
        norm = _normalize_name(name)
        if not norm:
            continue
        priority = exchange_priority.get(entry[exchange_idx], 99)
        if norm not in lookup or priority < lookup[norm][1]:
            lookup[norm] = (ticker.upper(), priority)

    result = {k: v[0] for k, v in lookup.items()}
    result.update(NAME_OVERRIDES)
    return result


def _load_cached_accession() -> str | None:
    """读取缓存的 IWB accession（30天内有效）。"""
    if not _CACHE_FILE.exists():
        return None
    try:
        data = json.loads(_CACHE_FILE.read_text())
        cached_at = datetime.fromisoformat(data["cached_at"])
        if datetime.now() - cached_at < timedelta(days=_CACHE_MAX_DAYS):
            return data["accession"]
    except Exception:
        pass
    return None


def _save_accession_cache(accession: str) -> None:
    """缓存 IWB accession 到文件。"""
    _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    _CACHE_FILE.write_text(json.dumps({
        "accession": accession,
        "cached_at": datetime.now().isoformat(),
    }))


def _find_iwb_accession() -> str:
    """从 iShares Trust 最新 NPORT-P 申报中找到 IWB 的 accession number。

    优先使用缓存（30天内有效），避免每次扫描 1400+ 文件。
    """
    cached = _load_cached_accession()
    if cached:
        log.info(f"使用缓存的 IWB accession: {cached}")
        return cached
    resp = requests.get(
        f"https://data.sec.gov/submissions/CIK{ISHARES_TRUST_CIK_PADDED}.json",
        headers=EDGAR_HEADERS,
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()

    filings = data["filings"]["recent"]
    nport_list = sorted(
        [
            (a, d)
            for f, d, a in zip(filings["form"], filings["filingDate"], filings["accessionNumber"])
            if f == "NPORT-P"
        ],
        key=lambda x: x[1],
        reverse=True,
    )

    log.info(f"扫描 {len(nport_list)} 个 NPORT-P 申报以找到 IWB...")
    for acc, filing_date in nport_list:
        acc_path = acc.replace("-", "")
        url = f"https://www.sec.gov/Archives/edgar/data/{ISHARES_TRUST_CIK}/{acc_path}/primary_doc.xml"
        try:
            r = requests.get(url, headers=EDGAR_HEADERS, timeout=10)
            if r.status_code == 429:
                log.warning("SEC rate limit 触发，等待 60s...")
                time.sleep(60)
                r = requests.get(url, headers=EDGAR_HEADERS, timeout=10)
            if r.status_code == 200:
                m = re.search(r"<seriesName>(.*?)</seriesName>", r.text)
                if m and m.group(1).strip() == "iShares Russell 1000 ETF":
                    log.info(f"找到 IWB NPORT-P: {acc} ({filing_date})")
                    _save_accession_cache(acc)
                    return acc
        except Exception:
            pass
        time.sleep(EDGAR_RATE_DELAY)

    raise ValueError("未在 iShares Trust NPORT-P 申报中找到 iShares Russell 1000 ETF")


def _parse_nport_holdings(xml_text: str, name_lookup: dict[str, str]) -> pd.DataFrame:
    """解析 NPORT-P XML，通过名称匹配获取 ticker。"""
    blocks = re.findall(r"<invstOrSec>(.*?)</invstOrSec>", xml_text, re.DOTALL)

    rows = []
    unmatched = 0
    for block in blocks:
        asset_m = re.search(r"<assetCat>(.*?)</assetCat>", block)
        asset_cat = asset_m.group(1).strip() if asset_m else ""
        if asset_cat and asset_cat not in ("EC", "EQ"):
            continue

        name_m = re.search(r"<name>(.*?)</name>", block)
        raw_name = name_m.group(1).strip() if name_m else ""
        if not raw_name:
            continue

        norm = _normalize_name(raw_name)
        ticker = name_lookup.get(norm)

        if ticker and _valid_us_ticker(ticker):
            rows.append({"ticker": ticker, "name": html.unescape(raw_name), "sector": None})
        else:
            unmatched += 1

    if unmatched:
        log.debug(f"名称匹配失败：{unmatched} 支（通常为外资股或特殊结构）")

    if not rows:
        return pd.DataFrame(columns=["ticker", "name", "sector"])
    df = pd.DataFrame(rows)
    # pandas 对全 None 列推断 float64（NaN），显式转为 Python None
    for col in df.columns:
        df[col] = [None if pd.isna(v) else v for v in df[col]]
    return df


def fetch_russell1000_data() -> pd.DataFrame:
    """从 SEC EDGAR NPORT-P 抓取 IWB 持仓作为 Russell 1000 成分股。"""
    name_lookup = _build_name_ticker_lookup()
    time.sleep(EDGAR_RATE_DELAY)

    acc = _find_iwb_accession()

    acc_path = acc.replace("-", "")
    url = f"https://www.sec.gov/Archives/edgar/data/{ISHARES_TRUST_CIK}/{acc_path}/primary_doc.xml"
    resp = requests.get(url, headers=EDGAR_HEADERS, timeout=30)
    resp.raise_for_status()

    df = _parse_nport_holdings(resp.text, name_lookup)
    df = df.where(pd.notnull(df), None)  # NaN → None（MySQL 不接受 NaN）
    log.info(f"Russell 1000 ETF (NPORT-P): 解析 {len(df)} 支成分股")
    return df[["ticker", "name", "sector"]]


def update_russell1000() -> tuple[int, int]:
    """更新 Russell 1000 成分股快照。

    Returns:
        (inserted_rows, constituent_count)
    """
    index_id = "RUSSELL1000"
    today = date.today()

    conn = get_conn()
    prev_date = get_last_snapshot_date(conn, index_id)
    conn.close()
    if prev_date == today:
        log.info("[RUSSELL1000] 今日已更新，跳过")
        return 0, 0

    df = fetch_russell1000_data()
    if df.empty:
        return 0, 0

    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT IGNORE INTO indices (index_id, name, etf_ticker, description) "
                "VALUES (%s, %s, %s, %s)",
                (index_id, "Russell 1000", "IWB", "Russell 1000 Large Cap Index"),
            )

        # 用 Python list 直接构建 rows，绕过 pandas NaN 问题
        tickers = df["ticker"].tolist()
        names = df["name"].tolist()
        ic_rows = [(index_id, today, t, n or None, None) for t, n in zip(tickers, names)]
        with conn.cursor() as cur:
            inserted = cur.executemany(
                "INSERT IGNORE INTO index_constituents "
                "(index_id, snapshot_date, ticker, name, sector) "
                "VALUES (%s, %s, %s, %s, %s)",
                ic_rows,
            )

        # 构造干净的 DataFrame 传给 register_stocks
        stocks_df = pd.DataFrame({
            "ticker": tickers,
            "name": [n or None for n in names],
            "sector": [None] * len(tickers),
        })
        register_stocks(conn, stocks_df)
        conn.commit()
        log.info(f"Russell 1000: {inserted} rows inserted, {len(df)} constituents")
        return inserted, len(df)
    finally:
        conn.close()


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    update_russell1000()
