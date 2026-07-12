"""进程级 Tushare 调用预算追踪。

- tick(api): 自增计数，由 client.call 驱动
- snapshot(): {total, per_api, elapsed_sec}
- report(): 单行字符串摘要
- precheck(client, api_list): 提前抽样调用，返回失败接口列表
"""
from __future__ import annotations

import logging
import time
from collections import Counter

log = logging.getLogger(__name__)

_total = 0
_per_api: Counter[str] = Counter()
_t0 = time.monotonic()


def reset() -> None:
    global _total, _per_api, _t0
    _total = 0
    _per_api = Counter()
    _t0 = time.monotonic()


def tick(api_name: str) -> None:
    global _total
    _total += 1
    _per_api[api_name] += 1


def snapshot() -> dict:
    return {
        "total": _total,
        "per_api": dict(_per_api),
        "elapsed_sec": round(time.monotonic() - _t0, 1),
    }


def report() -> str:
    s = snapshot()
    rate = s["total"] / max(s["elapsed_sec"], 0.1) * 60
    return f"calls={s['total']} elapsed={s['elapsed_sec']}s rate={rate:.1f}/min top={dict(_per_api.most_common(3))}"


# Tushare 接口最小 sample 调用参数
_SAMPLE_KWARGS = {
    "stock_basic": {"exchange": "SSE", "limit": 1},
    "fund_basic": {"market": "E", "limit": 1},
    "hs_const": {"hs_type": "SH"},
    "index_basic": {"market": "SSE"},
    "income_vip": {"period": "20231231", "fields": "ts_code,end_date"},
    "balancesheet_vip": {"period": "20231231", "fields": "ts_code,end_date"},
    "cashflow_vip": {"period": "20231231", "fields": "ts_code,end_date"},
    "fina_indicator_vip": {"period": "20231231", "fields": "ts_code,end_date"},
    "us_basic": {"limit": 1},
    "hk_basic": {"limit": 1},
    "index_weight": {"index_code": "000906.SH", "trade_date": "20240329"},
    "dividend": {"ts_code": "600519.SH"},
    "repurchase": {"start_date": "20240101", "end_date": "20240110"},
    "stk_holdertrade": {"start_date": "20240101", "end_date": "20240110"},
}


def precheck(client, api_list: list[str]) -> list[str]:
    """对每个接口跑 1 次最小调用，返回失败列表。"""
    failed: list[str] = []
    for api in api_list:
        kwargs = _SAMPLE_KWARGS.get(api, {})
        try:
            df = client.call(api, **kwargs)
            if df is None or df.empty:
                log.warning(f"precheck {api}: returned empty (might be ok or quota issue)")
        except Exception as e:
            log.error(f"precheck {api}: FAILED — {e}")
            failed.append(api)
    return failed
