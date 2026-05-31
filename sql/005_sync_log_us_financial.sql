-- Add 'us_financial' to sync_log.data_type ENUM for US fundamental data (futu).
-- Run once: mysql -h 192.168.8.9 -u root -p$DB_PASSWORD stocks < sql/005_sync_log_us_financial.sql

ALTER TABLE sync_log
  MODIFY COLUMN data_type
  ENUM('price','financial','stock_info','intraday_15m','intraday_60m','price_weekly','us_financial')
  NOT NULL;
