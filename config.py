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
START_DATE_US    = "2010-01-01"  # 默认历史起点

# yfinance (效率优先配置)
YF_BATCH_SIZE    = 40       # 每批 40 只
YF_RETRY_COUNT   = 3
YF_TIMEOUT       = 60
YF_LOOKBACK_DAYS = 7
YF_THREADS       = False    # 单线程避免限速
YF_BATCH_DELAY_BASE = 15.0  # batch 基础间隔 15 秒
YF_BATCH_DELAY_JITTER = 3.0 # ±3 秒随机波动

# A-share / HK source delays (akshare is sometimes flaky; serial)
AKSHARE_RETRY_COUNT = 5
AKSHARE_RETRY_DELAY = 3.0
AKSHARE_REQUEST_DELAY = 1.5  # between per-stock calls

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

# Tushare
TUSHARE_TOKEN = os.getenv("TUSHARE_TOKEN", "")
TUSHARE_RATE_INTERVAL = float(os.getenv("TUSHARE_RATE_INTERVAL", "0.15"))  # 0.15=400/min, 0.08=800/min
TUSHARE_BACKFILL_START = "20100101"  # YYYYMMDD for Tushare APIs
TUSHARE_RETRY_COUNT = 3
TUSHARE_RETRY_DELAY = 5.0
