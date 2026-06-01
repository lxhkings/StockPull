#!/usr/bin/env python3
"""一次性探测 Futu quote/F10 接口限频(n 次/30s)。突发计数法。

用法:
    uv run python scripts/probe_futu_limits.py            # 全量 21 接口
    uv run python scripts/probe_futu_limits.py --only get_company_profile  # 单接口(冒烟)
前置:OpenD 已启动登录于 127.0.0.1:11111;勿与生产 backfill 并行。
"""
from __future__ import annotations

RET_OK = 0
FREQ_PATTERNS = (
    "频率", "限频", "frequent", "frequency", "too many", "rate limit", "请求过于",
)


def classify(ret: int, data) -> str:
    """归类单次调用结果:OK / FREQ / OTHER。"""
    if ret == RET_OK:
        return "OK"
    msg = str(data).lower()
    if any(p.lower() in msg for p in FREQ_PATTERNS):
        return "FREQ"
    return "OTHER"
