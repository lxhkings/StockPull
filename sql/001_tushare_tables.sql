-- Tushare backfill: 5 new tables for ETF, HK Connect, periodic K, and financial data
-- Run: mysql -h 192.168.8.9 -u root -p$DB_PASSWORD stocks < sql/001_tushare_tables.sql

-- ETF 基础信息（A 股，含场内场外）
CREATE TABLE IF NOT EXISTS etf_basic (
    ts_code     VARCHAR(20)  NOT NULL,
    name        VARCHAR(100),
    management  VARCHAR(100),
    custodian   VARCHAR(100),
    fund_type   VARCHAR(20),
    market      VARCHAR(10),         -- 'E' 场内 / 'O' 场外
    list_date   DATE,
    issue_date  DATE,
    delist_date DATE,
    status      VARCHAR(2),          -- 'L' 上市 / 'D' 退市 / 'P' 暂停
    PRIMARY KEY (ts_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 沪深港通标的
CREATE TABLE IF NOT EXISTS hk_connect_universe (
    hs_type     VARCHAR(4)  NOT NULL,   -- 'SH' 沪股通 / 'SZ' 深股通
    ts_code     VARCHAR(20) NOT NULL,
    name        VARCHAR(100),
    in_date     DATE,
    out_date    DATE,
    PRIMARY KEY (hs_type, ts_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 周 K
CREATE TABLE IF NOT EXISTS prices_weekly (
    ticker  VARCHAR(20) NOT NULL,
    date    DATE        NOT NULL,
    open    DECIMAL(10,4),
    high    DECIMAL(10,4),
    low     DECIMAL(10,4),
    close   DECIMAL(10,4),
    volume  BIGINT,
    PRIMARY KEY (ticker, date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 月 K
CREATE TABLE IF NOT EXISTS prices_monthly (
    ticker  VARCHAR(20) NOT NULL,
    date    DATE        NOT NULL,
    open    DECIMAL(10,4),
    high    DECIMAL(10,4),
    low     DECIMAL(10,4),
    close   DECIMAL(10,4),
    volume  BIGINT,
    PRIMARY KEY (ticker, date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 财务接口通用结构：原始字段塞 raw_payload JSON，常用查询列单独提出来
CREATE TABLE IF NOT EXISTS fin_income (
    ts_code     VARCHAR(20) NOT NULL,
    end_date    DATE        NOT NULL,
    ann_date    DATE,
    f_ann_date  DATE,
    report_type VARCHAR(4)  NOT NULL,   -- 1=合并报表 2=单季合并 ... (Tushare 文档)
    comp_type   VARCHAR(4),
    raw_payload JSON,
    PRIMARY KEY (ts_code, end_date, report_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS fin_balancesheet (
    ts_code     VARCHAR(20) NOT NULL,
    end_date    DATE        NOT NULL,
    ann_date    DATE,
    f_ann_date  DATE,
    report_type VARCHAR(4)  NOT NULL,
    comp_type   VARCHAR(4),
    raw_payload JSON,
    PRIMARY KEY (ts_code, end_date, report_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS fin_cashflow (
    ts_code     VARCHAR(20) NOT NULL,
    end_date    DATE        NOT NULL,
    ann_date    DATE,
    f_ann_date  DATE,
    report_type VARCHAR(4)  NOT NULL,
    comp_type   VARCHAR(4),
    raw_payload JSON,
    PRIMARY KEY (ts_code, end_date, report_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS fin_indicator (
    ts_code     VARCHAR(20) NOT NULL,
    end_date    DATE        NOT NULL,
    ann_date    DATE,
    raw_payload JSON,
    PRIMARY KEY (ts_code, end_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
