"""Ticker format conversion across markets and source APIs.

Internal canonical formats:
  US: bare uppercase, e.g., AAPL, BRK.B, BRK-B
  A-share SH: <6-digit>.SH, e.g., 600519.SH, 688981.SH
  A-share SZ: <6-digit>.SZ, e.g., 000001.SZ, 300750.SZ
  HK: <5-digit>.HK, e.g., 00700.HK, 09988.HK
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class Market(str, Enum):
    US = "us"
    CN = "cn"
    HK = "hk"


@dataclass(frozen=True)
class ParsedTicker:
    code: str
    suffix: Optional[str]   # 'SH' / 'SZ' / 'HK' / None (US)


_SUFFIX_RE = re.compile(r"^(?P<code>[A-Z0-9.\-]+)\.(?P<suffix>SH|SZ|HK)$")


def parse_ticker(ticker: str) -> ParsedTicker:
    t = ticker.strip().upper()
    m = _SUFFIX_RE.match(t)
    if m:
        return ParsedTicker(code=m.group("code"), suffix=m.group("suffix"))
    return ParsedTicker(code=t, suffix=None)


def infer_market(ticker: str) -> Market:
    p = parse_ticker(ticker)
    if p.suffix in ("SH", "SZ"):
        return Market.CN
    if p.suffix == "HK":
        return Market.HK
    return Market.US


def infer_a_exchange(code: str) -> str:
    """A-share code → SH or SZ (per Shanghai/Shenzhen prefix rules)."""
    if code.startswith(("6", "9")) or code.startswith("68"):
        return "SH"
    if code.startswith(("0", "3", "2")):
        return "SZ"
    raise ValueError(f"Unknown A-share prefix: {code}")


def to_yfinance_us(ticker: str) -> str:
    """yfinance: dot → dash (BRK.B → BRK-B)."""
    return ticker.upper().replace(".", "-")
