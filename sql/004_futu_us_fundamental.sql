-- 美股基本面数据 (Futu OpenAPI)。通用模式：raw_payload JSON 兜底 + 关键列抽取。
-- Run: mysql -h 192.168.8.9 -u root -p$DB_PASSWORD stocks < sql/004_futu_us_fundamental.sql

-- ── P0：财务三表 + 关键指标 ──
-- ticker 为 canonical 格式（无前缀，如 AAPL）。ann_date 由 earnings 接口回填。
CREATE TABLE IF NOT EXISTS us_fin_income (
    ticker         VARCHAR(20) NOT NULL,
    period_end     DATE        NOT NULL,
    financial_type VARCHAR(4)  NOT NULL,
    fiscal_year    VARCHAR(8),
    period_text    VARCHAR(20),
    ann_date       DATE,
    currency_code  VARCHAR(8),
    accounting_standards VARCHAR(40),
    raw_payload    JSON,
    PRIMARY KEY (ticker, period_end, financial_type),
    INDEX idx_income_period_text (ticker, period_text),
    INDEX idx_income_ann (ticker, ann_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS us_fin_balance (
    ticker         VARCHAR(20) NOT NULL,
    period_end     DATE        NOT NULL,
    financial_type VARCHAR(4)  NOT NULL,
    fiscal_year    VARCHAR(8),
    period_text    VARCHAR(20),
    ann_date       DATE,
    currency_code  VARCHAR(8),
    accounting_standards VARCHAR(40),
    raw_payload    JSON,
    PRIMARY KEY (ticker, period_end, financial_type),
    INDEX idx_balance_period_text (ticker, period_text),
    INDEX idx_balance_ann (ticker, ann_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS us_fin_cashflow (
    ticker         VARCHAR(20) NOT NULL,
    period_end     DATE        NOT NULL,
    financial_type VARCHAR(4)  NOT NULL,
    fiscal_year    VARCHAR(8),
    period_text    VARCHAR(20),
    ann_date       DATE,
    currency_code  VARCHAR(8),
    accounting_standards VARCHAR(40),
    raw_payload    JSON,
    PRIMARY KEY (ticker, period_end, financial_type),
    INDEX idx_cashflow_period_text (ticker, period_text),
    INDEX idx_cashflow_ann (ticker, ann_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS us_fin_indicator (
    ticker         VARCHAR(20) NOT NULL,
    period_end     DATE        NOT NULL,
    financial_type VARCHAR(4)  NOT NULL,
    fiscal_year    VARCHAR(8),
    period_text    VARCHAR(20),
    ann_date       DATE,
    currency_code  VARCHAR(8),
    accounting_standards VARCHAR(40),
    raw_payload    JSON,
    PRIMARY KEY (ticker, period_end, financial_type),
    INDEX idx_indicator_period_text (ticker, period_text),
    INDEX idx_indicator_ann (ticker, ann_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ── P0：财报发布日（供 PIT 回填）──
CREATE TABLE IF NOT EXISTS us_earnings_dates (
    ticker         VARCHAR(20) NOT NULL,
    period_text    VARCHAR(20) NOT NULL,
    fiscal_year    VARCHAR(8),
    financial_type VARCHAR(4),
    pub_date       DATE,
    raw_payload    JSON,
    PRIMARY KEY (ticker, period_text)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ── P0：分红派息 ──
CREATE TABLE IF NOT EXISTS us_dividends (
    ticker       VARCHAR(20) NOT NULL,
    ex_date      DATE        NOT NULL,
    pub_date     DATE,
    record_date  DATE,
    payable_date DATE,
    raw_payload  JSON,
    PRIMARY KEY (ticker, ex_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ── P0：拆/合股 ──
CREATE TABLE IF NOT EXISTS us_splits (
    ticker      VARCHAR(20) NOT NULL,
    ex_date     DATE        NOT NULL,
    raw_payload JSON,
    PRIMARY KEY (ticker, ex_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ── P1：流通股本 + 市值（每日快照）──
CREATE TABLE IF NOT EXISTS us_shares_daily (
    ticker              VARCHAR(20) NOT NULL,
    date                DATE        NOT NULL,
    issued_shares       BIGINT,
    outstanding_shares  BIGINT,
    total_market_val    DECIMAL(24,2),
    circular_market_val DECIMAL(24,2),
    raw_payload         JSON,
    PRIMARY KEY (ticker, date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ── P1：分析师一致预期（每日快照）──
CREATE TABLE IF NOT EXISTS us_analyst_consensus (
    ticker         VARCHAR(20) NOT NULL,
    snapshot_date  DATE        NOT NULL,
    target_high    DECIMAL(12,4),
    target_avg     DECIMAL(12,4),
    target_low     DECIMAL(12,4),
    rating         VARCHAR(20),
    total_analysts INT,
    buy_pct        DECIMAL(6,2),
    hold_pct       DECIMAL(6,2),
    sell_pct       DECIMAL(6,2),
    raw_payload    JSON,
    PRIMARY KEY (ticker, snapshot_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
