-- 美股扩展数据 (Futu OpenAPI Phase 2)。16 张表。
-- Run: mysql -h 192.168.8.9 -u root -p$DB_PASSWORD stocks < sql/005_futu_us_extended.sql

-- ── Batch 1：估值 + 分析师深度 + 股东/内部人 + 公司元数据 + 运营效率 ──

-- 1. 公司元数据（EAV 模式，18 字段异构）
CREATE TABLE IF NOT EXISTS us_company_profile (
    ticker      VARCHAR(20)  NOT NULL,
    field_name  VARCHAR(40)  NOT NULL,
    field_value TEXT,
    updated_at  DATE,
    PRIMARY KEY (ticker, field_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 2. 分部营收
CREATE TABLE IF NOT EXISTS us_revenue_breakdown (
    ticker            VARCHAR(20) NOT NULL,
    period_text       VARCHAR(20) NOT NULL,
    type              TINYINT     NOT NULL,
    item_name         VARCHAR(80) NOT NULL,
    main_oper_income  DOUBLE,
    ratio             DOUBLE,
    updated_at        DATE,
    PRIMARY KEY (ticker, period_text, type, item_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 3. 财报日涨跌
CREATE TABLE IF NOT EXISTS us_earnings_price_move (
    ticker          VARCHAR(20) NOT NULL,
    period_text     VARCHAR(20) NOT NULL,
    day_offset      SMALLINT    NOT NULL,
    fiscal_year     SMALLINT,
    financial_type  VARCHAR(4),
    pub_trading_day DATE,
    trading_day     DATE,
    open            DOUBLE,
    close           DOUBLE,
    high            DOUBLE,
    low             DOUBLE,
    volume          BIGINT,
    turnover        DOUBLE,
    implied_vol     DOUBLE,
    history_vol     DOUBLE,
    raw_payload     JSON,
    PRIMARY KEY (ticker, period_text, day_offset)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 4. 估值快照
CREATE TABLE IF NOT EXISTS us_valuation_snapshot (
    ticker          VARCHAR(20) NOT NULL,
    snapshot_date   DATE        NOT NULL,
    pe_ttm          DOUBLE,
    pe_percentile   DOUBLE,
    pe_avg          DOUBLE,
    pb              DOUBLE,
    pb_percentile   DOUBLE,
    ps_ttm          DOUBLE,
    ps_percentile   DOUBLE,
    plate_code      VARCHAR(20),
    plate_name      VARCHAR(60),
    plate_ranking   INT,
    raw_payload     JSON,
    PRIMARY KEY (ticker, snapshot_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 5. 机构评级变动
CREATE TABLE IF NOT EXISTS us_rating_summary (
    ticker                  VARCHAR(20)  NOT NULL,
    snapshot_date           DATE         NOT NULL,
    institution_uid         VARCHAR(64)  NOT NULL,
    institution_name        VARCHAR(100),
    institution_picture_url VARCHAR(200),
    rating                  VARCHAR(20),
    target_price            DOUBLE,
    update_time             DATETIME,
    raw_payload             JSON,
    PRIMARY KEY (ticker, snapshot_date, institution_uid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 6. Morningstar 评级
CREATE TABLE IF NOT EXISTS us_morningstar (
    ticker              VARCHAR(20) NOT NULL,
    snapshot_date       DATE        NOT NULL,
    star_rating         TINYINT,
    star_update_time    DATETIME,
    fair_value          DOUBLE,
    economic_moat       VARCHAR(10),
    uncertainty         VARCHAR(10),
    capital_allocation  VARCHAR(10),
    analyst_name        VARCHAR(60),
    analyst_update_time DATETIME,
    raw_payload         JSON,
    PRIMARY KEY (ticker, snapshot_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 7. 股东概览（main + type 合并，holder_category 区分）
CREATE TABLE IF NOT EXISTS us_shareholders_overview (
    ticker          VARCHAR(20) NOT NULL,
    period_text     VARCHAR(20) NOT NULL,
    holder_category VARCHAR(20) NOT NULL,
    holder_name     VARCHAR(100),
    holder_pct      DOUBLE,
    holder_id       BIGINT,
    raw_payload     JSON,
    PRIMARY KEY (ticker, period_text, holder_category, holder_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 8. 股东增减持
CREATE TABLE IF NOT EXISTS us_holding_changes (
    ticker              VARCHAR(20) NOT NULL,
    period_text         VARCHAR(20) NOT NULL,
    holder_id           BIGINT      NOT NULL,
    holder_name         VARCHAR(100),
    holder_type         VARCHAR(40),
    share_change_num    BIGINT,
    shares_change_price BIGINT,
    share_ratio         DOUBLE,
    holding_date        DATE,
    raw_payload         JSON,
    PRIMARY KEY (ticker, period_text, holder_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 9. 机构持仓汇总
CREATE TABLE IF NOT EXISTS us_institutional (
    ticker                  VARCHAR(20) NOT NULL,
    period_text             VARCHAR(20) NOT NULL,
    institution_quantity    INT,
    institution_qty_change  INT,
    holder_quantity         BIGINT,
    holder_qty_change       BIGINT,
    holder_pct              DOUBLE,
    holder_pct_change       DOUBLE,
    update_time             DATETIME,
    raw_payload             JSON,
    PRIMARY KEY (ticker, period_text)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 10. 内部人持股（时序快照，snapshot_date 进 PK）
CREATE TABLE IF NOT EXISTS us_insider_holders (
    ticker              VARCHAR(20) NOT NULL,
    holder_id           BIGINT      NOT NULL,
    holder_name         VARCHAR(100),
    title               VARCHAR(100),
    holder_quantity     BIGINT,
    holder_pct          DOUBLE,
    all_count           INT,
    insider_total_count INT,
    insider_bought_count INT,
    insider_sold_count  INT,
    snapshot_date       DATE        NOT NULL,
    raw_payload         JSON,
    PRIMARY KEY (ticker, holder_id, snapshot_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 11. 内部人交易 (Form 4)
CREATE TABLE IF NOT EXISTS us_insider_trades (
    ticker                  VARCHAR(20) NOT NULL,
    holder_id               BIGINT      NOT NULL,
    min_trade_date          DATE        NOT NULL,
    holder_name             VARCHAR(100),
    title                   VARCHAR(100),
    transaction_type        VARCHAR(60) NOT NULL,
    trade_shares            BIGINT,
    min_price               DOUBLE,
    max_price               DOUBLE,
    security_holder_quantity DOUBLE,
    security_description    VARCHAR(40),
    source_group_name       VARCHAR(20),
    raw_payload             JSON,
    PRIMARY KEY (ticker, holder_id, min_trade_date, transaction_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 12. 运营效率
CREATE TABLE IF NOT EXISTS us_op_efficiency (
    ticker                  VARCHAR(20) NOT NULL,
    period_text             VARCHAR(20) NOT NULL,
    end_date                DATE,
    employee_num            INT,
    employee_num_yoy        DOUBLE,
    income_per_capita       DOUBLE,
    income_per_capita_yoy   DOUBLE,
    profit_per_capita       DOUBLE,
    profit_per_capita_yoy   DOUBLE,
    net_profit_per_capita   DOUBLE,
    net_profit_per_capita_yoy DOUBLE,
    currency_code           VARCHAR(8),
    raw_payload             JSON,
    PRIMARY KEY (ticker, period_text)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ── Batch 2：资金流 + 卖空 ──

-- 13. 日频资金流
CREATE TABLE IF NOT EXISTS us_capital_flow (
    ticker          VARCHAR(20) NOT NULL,
    date            DATE        NOT NULL,
    in_flow         DOUBLE,
    super_in_flow   DOUBLE,
    big_in_flow     DOUBLE,
    mid_in_flow     DOUBLE,
    sml_in_flow     DOUBLE,
    main_in_flow    DOUBLE,
    raw_payload     JSON,
    PRIMARY KEY (ticker, date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 14. 资金分布（当日快照）
CREATE TABLE IF NOT EXISTS us_capital_distribution (
    ticker              VARCHAR(20) NOT NULL,
    date                DATE        NOT NULL,
    capital_in_super    DOUBLE,
    capital_in_big      DOUBLE,
    capital_in_mid      DOUBLE,
    capital_in_small    DOUBLE,
    capital_out_super   DOUBLE,
    capital_out_big     DOUBLE,
    capital_out_mid     DOUBLE,
    capital_out_small   DOUBLE,
    update_time         DATETIME,
    raw_payload         JSON,
    PRIMARY KEY (ticker, date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 15. 空头持仓（3 值返回接口）
CREATE TABLE IF NOT EXISTS us_short_interest (
    ticker                 VARCHAR(20) NOT NULL,
    timestamp              DATE        NOT NULL,
    shares_short           BIGINT,
    short_percent          DOUBLE,
    avg_daily_share_volume BIGINT,
    days_to_cover          DOUBLE,
    close_price            DOUBLE,
    last_close_price       DOUBLE,
    raw_payload            JSON,
    PRIMARY KEY (ticker, timestamp)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 16. 每日卖空量（3 值返回接口）
CREATE TABLE IF NOT EXISTS us_daily_short_volume (
    ticker                VARCHAR(20) NOT NULL,
    timestamp             DATE        NOT NULL,
    total_shares_short    BIGINT,
    nasdaq_shares_short   BIGINT,
    nyse_shares_short     BIGINT,
    short_percent         DOUBLE,
    volume                BIGINT,
    close_price           DOUBLE,
    last_close_price      DOUBLE,
    daily_trade_avg_ratio DOUBLE,
    raw_payload           JSON,
    PRIMARY KEY (ticker, timestamp)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
