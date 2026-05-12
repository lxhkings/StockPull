-- 清理 yfinance 风格（含 dash）的 US 数据，为 Tushare backfill 做准备。
-- US 判定：ticker 不以 .SH/.SZ/.BJ/.HK 结尾。
-- 顺序：从依赖叶子向根删，避免外键问题（虽然现 schema 无 FK，保持习惯）。
--
-- 注意：当前数据库中 US tickers 已是 dot 格式（BRK.B 等），此脚本无需执行。
-- 保留此文件以备将来需要清理类似数据时使用。

-- DELETE FROM prices
-- WHERE ticker LIKE '%-%'
--   AND ticker NOT LIKE '%.SH' AND ticker NOT LIKE '%.SZ' AND ticker NOT LIKE '%.BJ' AND ticker NOT LIKE '%.HK';

-- DELETE FROM sync_log
-- WHERE ticker LIKE '%-%'
--   AND ticker NOT LIKE '%.SH' AND ticker NOT LIKE '%.SZ' AND ticker NOT LIKE '%.BJ' AND ticker NOT LIKE '%.HK';

-- DELETE FROM index_constituents
-- WHERE ticker LIKE '%-%'
--   AND ticker NOT LIKE '%.SH' AND ticker NOT LIKE '%.SZ' AND ticker NOT LIKE '%.BJ' AND ticker NOT LIKE '%.HK';

-- DELETE FROM constituent_changes
-- WHERE ticker LIKE '%-%'
--   AND ticker NOT LIKE '%.SH' AND ticker NOT LIKE '%.SZ' AND ticker NOT LIKE '%.BJ' AND ticker NOT LIKE '%.HK';

-- DELETE FROM stocks
-- WHERE ticker LIKE '%-%'
--   AND ticker NOT LIKE '%.SH' AND ticker NOT LIKE '%.SZ' AND ticker NOT LIKE '%.BJ' AND ticker NOT LIKE '%.HK';
