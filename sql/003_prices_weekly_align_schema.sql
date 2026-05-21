-- Align prices_weekly schema to match prices table exactly.
-- Adds: id (auto_increment PK), created_at, upgrades DECIMAL(10,4)→(14,4),
--       replaces composite PK with UNIQUE KEY + separate PK on id.
-- Run once: mysql -h 192.168.8.9 -u root -p$DB_PASSWORD stocks < sql/003_prices_weekly_align_schema.sql

ALTER TABLE prices_weekly
  DROP PRIMARY KEY,
  ADD COLUMN id bigint(20) NOT NULL AUTO_INCREMENT FIRST,
  ADD PRIMARY KEY (id),
  MODIFY COLUMN open    decimal(14,4) DEFAULT NULL,
  MODIFY COLUMN high    decimal(14,4) DEFAULT NULL,
  MODIFY COLUMN low     decimal(14,4) DEFAULT NULL,
  MODIFY COLUMN close   decimal(14,4) DEFAULT NULL,
  ADD COLUMN created_at timestamp NOT NULL DEFAULT current_timestamp() AFTER volume,
  ADD UNIQUE KEY uq_ticker_date (ticker, date),
  ADD KEY idx_ticker (ticker),
  ADD KEY idx_date (date);
