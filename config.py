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

# A-share ETF (后复权日线 via tushare fund_daily × fund_adj)
# GICS 11 行业 + A股主题 + 宽基指数
CN_SECTOR_ETFS = {
    # GICS 11 行业
    "515220.SH": {"name": "煤炭ETF",     "gics": "Energy"},
    "512400.SH": {"name": "有色金属ETF", "gics": "Materials"},
    "512660.SH": {"name": "军工ETF",     "gics": "Industrials"},
    "159996.SZ": {"name": "家电ETF",     "gics": "ConsumerDiscretionary"},
    "512690.SH": {"name": "酒ETF",       "gics": "ConsumerStaples"},
    "512170.SH": {"name": "医疗ETF",     "gics": "HealthCare"},
    "512010.SH": {"name": "医药ETF",     "gics": "HealthCare"},
    "512800.SH": {"name": "银行ETF",     "gics": "Financials"},
    "512000.SH": {"name": "券商ETF",     "gics": "Financials"},
    "512720.SH": {"name": "计算机ETF",   "gics": "InformationTechnology"},
    "512480.SH": {"name": "半导体ETF",   "gics": "InformationTechnology"},
    "515050.SH": {"name": "5G通信ETF",   "gics": "CommunicationServices"},
    "159611.SZ": {"name": "电力ETF",     "gics": "Utilities"},
    "512200.SH": {"name": "房地产ETF",   "gics": "RealEstate"},
    # A股主题
    "515790.SH": {"name": "光伏ETF",     "gics": "Theme.Solar"},
    "515030.SH": {"name": "新能源车ETF", "gics": "Theme.NEV"},
    "159995.SZ": {"name": "芯片ETF",     "gics": "Theme.Chip"},
    # 行业大盘
    "159928.SZ": {"name": "消费ETF",     "gics": "Consumer"},
    "515000.SH": {"name": "科技ETF",     "gics": "Technology"},
    # 宽基指数
    "510300.SH": {"name": "沪深300ETF",  "gics": "Broad.CSI300"},
    "159915.SZ": {"name": "创业板ETF",   "gics": "Broad.ChiNext"},
    "588000.SH": {"name": "科创50ETF",   "gics": "Broad.STAR50"},
}

# Tushare
TUSHARE_TOKEN = os.getenv("TUSHARE_TOKEN", "")
TUSHARE_RATE_INTERVAL = float(os.getenv("TUSHARE_RATE_INTERVAL", "0.15"))  # 0.15=400/min, 0.08=800/min
TUSHARE_BACKFILL_START = "20100101"  # YYYYMMDD for Tushare APIs
TUSHARE_RETRY_COUNT = 3
TUSHARE_RETRY_DELAY = 5.0

# Futu OpenAPI (美股基本面入库 via 本地 OpenD)
FUTU_OPEND_HOST    = os.getenv("FUTU_OPEND_HOST", "127.0.0.1")
FUTU_OPEND_PORT    = int(os.getenv("FUTU_OPEND_PORT", "11111"))
# 每接口限频（探测实测，n 次/30s）。只列比默认快的；其余走默认。
# 0.625 = 60/30s；0.312 = 120-cap；默认 1.25 = 30/30s + 20% 余量。
FUTU_LIMIT_INTERVALS = {
    "get_market_snapshot":                0.625,
    "get_capital_distribution":           0.625,
    "get_company_operational_efficiency": 0.312,
    "get_insider_holder_list":            0.312,
    "get_insider_trade_list":             0.312,
}
FUTU_DEFAULT_INTERVAL = 1.25
FUTU_RETRY_COUNT   = 3
FUTU_RETRY_DELAY   = 3.0
FUTU_BACKFILL_START = "2010-01-01"   # 财报历史起点
FUTU_FINANCIAL_TYPE = 10             # 10=单季报+年报（Futu financial_type 枚举）
FUTU_CURRENCY_CODE  = "USD"          # 财报币种统一 USD
