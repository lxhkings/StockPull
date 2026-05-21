-- Add 'price_weekly' to sync_log.data_type ENUM for US weekly ingest.
-- Run once: mysql -h 192.168.8.9 -u root -p$DB_PASSWORD stocks < sql/002_sync_log_price_weekly.sql

ALTER TABLE sync_log
  MODIFY COLUMN data_type
  ENUM('price','financial','stock_info','intraday_15m','intraday_60m','price_weekly')
  NOT NULL;
