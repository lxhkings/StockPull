-- cn_holdertrade.holder_name 太窄：Tushare 偶尔把多个关联方名称用逗号拼在一个字段里返回，
-- 实测已见 170 字符（VARCHAR(100) 装不下），给足余量放宽到 500。
-- Run: mysql -h 192.168.8.9 -u root -p$DB_PASSWORD stocks < sql/010_cn_holdertrade_widen_holder_name.sql

ALTER TABLE cn_holdertrade MODIFY COLUMN holder_name VARCHAR(500) NOT NULL;
