-- cn_valuation_snapshot 补股息率字段（daily_basic 接口本来就返回，之前未收录）
ALTER TABLE cn_valuation_snapshot ADD COLUMN dv_ratio DOUBLE AFTER circ_mv;
