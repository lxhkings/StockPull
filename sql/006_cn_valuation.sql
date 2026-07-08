-- CN 每日估值快照（Tushare daily_basic，全市场批量按 trade_date）
-- Run: mysql -h 192.168.8.9 -u root -p$DB_PASSWORD stocks < sql/006_cn_valuation.sql

CREATE TABLE IF NOT EXISTS cn_valuation_snapshot (
    ts_code         VARCHAR(20) NOT NULL,
    trade_date      DATE        NOT NULL,
    close           DOUBLE,
    turnover_rate   DOUBLE,
    volume_ratio    DOUBLE,
    pe              DOUBLE,
    pe_ttm          DOUBLE,
    pb              DOUBLE,
    ps              DOUBLE,
    ps_ttm          DOUBLE,
    total_mv        DOUBLE,
    circ_mv         DOUBLE,
    PRIMARY KEY (ts_code, trade_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
