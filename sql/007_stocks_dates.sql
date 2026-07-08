-- 补充 stocks.list_date/delist_date，支撑全A股 PIT universe 事件构造
-- Run: mysql -h 192.168.8.9 -u root -p$DB_PASSWORD stocks < sql/007_stocks_dates.sql

ALTER TABLE stocks
    ADD COLUMN list_date DATE AFTER is_active,
    ADD COLUMN delist_date DATE AFTER list_date;
