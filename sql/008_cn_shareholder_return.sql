-- A 股股东回报：分红送股 / 股票回购 / 股东增减持
-- Run: mysql -h 192.168.8.9 -u root -p$DB_PASSWORD stocks < sql/008_cn_shareholder_return.sql

CREATE TABLE IF NOT EXISTS cn_dividend (
    ts_code      VARCHAR(20) NOT NULL,
    end_date     DATE        NOT NULL,   -- 分红年度
    ann_date     DATE        NOT NULL,   -- 预案公告日
    div_proc     VARCHAR(20),            -- 实施进度
    stk_div      DOUBLE,
    stk_bo_rate  DOUBLE,
    stk_co_rate  DOUBLE,
    cash_div     DOUBLE,
    cash_div_tax DOUBLE,
    record_date  DATE,
    ex_date      DATE,
    pay_date     DATE,
    div_listdate DATE,
    imp_ann_date DATE,
    base_date    DATE,
    base_share   DOUBLE,
    PRIMARY KEY (ts_code, end_date, ann_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS cn_repurchase (
    ts_code    VARCHAR(20) NOT NULL,
    ann_date   DATE        NOT NULL,
    end_date   DATE        NOT NULL,     -- 截止日期
    proc       VARCHAR(20),
    exp_date   DATE,
    vol        DOUBLE,
    amount     DOUBLE,
    high_limit DOUBLE,
    low_limit  DOUBLE,
    PRIMARY KEY (ts_code, ann_date, end_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS cn_holdertrade (
    ts_code      VARCHAR(20) NOT NULL,
    ann_date     DATE        NOT NULL,
    holder_name  VARCHAR(100) NOT NULL,
    holder_type  VARCHAR(4),
    in_de        VARCHAR(4)  NOT NULL,
    change_vol   DOUBLE,
    change_ratio DOUBLE,
    after_share  DOUBLE,
    after_ratio  DOUBLE,
    avg_price    DOUBLE,
    total_share  DOUBLE,
    begin_date   DATE,
    close_date   DATE,
    PRIMARY KEY (ts_code, ann_date, holder_name, in_de)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
