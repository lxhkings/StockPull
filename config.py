"""Global configuration. Reads secrets from .env (python-dotenv).

Per-market history depths and ingest defaults live here.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# Database -- reads from .env, no fallback for password
DB = {
    "host":       os.getenv("DB_HOST", "192.168.8.9"),
    "port":       int(os.getenv("DB_PORT", "3306")),
    "user":       os.getenv("DB_USER", "root"),
    "password":   os.environ["DB_PASSWORD"],   # required, raises KeyError if missing
    "database":   os.getenv("DB_NAME", "stocks"),
    "charset":    "utf8mb4",
    "autocommit": False,
}

# History depths per market
HISTORY_YEARS_US = 5
HISTORY_YEARS_CN = 15
HISTORY_YEARS_HK = 15
START_DATE_CN    = "2010-01-01"
START_DATE_HK    = "2010-01-01"

# yfinance (carried over from stock_system)
YF_BATCH_SIZE    = 20
YF_RETRY_COUNT   = 3
YF_TIMEOUT       = 30
YF_LOOKBACK_DAYS = 7
YF_THREADS       = False
YF_BATCH_DELAY   = 2.0

# A-share / HK source delays (akshare is sometimes flaky; serial)
AKSHARE_RETRY_COUNT = 3
AKSHARE_RETRY_DELAY = 2.0
AKSHARE_REQUEST_DELAY = 0.5  # between per-stock calls

# Reconcile tolerance for two-source comparison
RECONCILE_PRICE_TOLERANCE = 0.005   # 0.5%

# Index metadata. etf required by indices.etf_ticker NOT NULL.
INDEX_CONFIG = {
    "SP500": {
        "name":   "S&P 500",
        "source": "github",
        "etf":    "IVV",
        "market": "us",
        "description": "iShares Core S&P 500 ETF",
    },
    "CSI800": {
        "name":   "中证800",
        "source": "akshare",
        "etf":    "510800",
        "market": "cn",
        "description": "中证800ETF (华夏)",
        "ak_symbol": "000906",
    },
    "HSI": {
        "name":   "恒生指数",
        "source": "akshare",
        "etf":    "2800.HK",
        "market": "hk",
        "description": "盈富基金 Tracker Fund",
        "ak_symbol": "HSI",
    },
}

INDEX_DELAY = 2.0   # delay between index updates (carried over)
