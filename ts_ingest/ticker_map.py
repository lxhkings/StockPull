"""项目 ticker ↔ Tushare ts_code 转换。

A 股 (`600519.SH`) 和 HK (`00700.HK`) 在两边格式一致；
仅指数代码需要显式映射。
"""
from __future__ import annotations

INDEX_TO_TS_CODE = {
    "CSI800": "000906.SH",
    "HSI": "HSI",         # Tushare 港股指数代码
    "SP500": "SPX",       # Tushare 美股指数（如不可用，由 precheck 报告）
}


def index_id_to_ts_code(index_id: str) -> str:
    if index_id not in INDEX_TO_TS_CODE:
        raise KeyError(f"unknown index_id {index_id!r}")
    return INDEX_TO_TS_CODE[index_id]


def is_a_share(ticker: str) -> bool:
    return ticker.endswith((".SH", ".SZ", ".BJ"))


def is_hk(ticker: str) -> bool:
    return ticker.endswith(".HK")


def is_us(ticker: str) -> bool:
    return not (is_a_share(ticker) or is_hk(ticker))


def ts_code_to_canonical(ts_code: str) -> str:
    """目前 1:1 透传；预留为未来格式调整的钩子。"""
    return ts_code
