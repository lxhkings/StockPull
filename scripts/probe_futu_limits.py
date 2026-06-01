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


CAP = 120          # burst 安全上限
MARGIN = 0.8       # 推荐速率留 20% 余量


def summarize_rounds(interface: str, rounds: list[int], raw_msg: str) -> dict:
    """聚合某接口多轮 burst 结果。rounds 含 -1 → SKIP;min ≥ CAP → NO-LIMIT;否则取 min。"""
    base = {"interface": interface, "raw_msg": raw_msg}
    if any(n < 0 for n in rounds):
        return {**base, "status": "SKIP", "n_per_30s": None,
                "fastest_interval": None, "recommended_interval": None}
    n = min(rounds)
    status = "NO-LIMIT@cap" if n >= CAP else "OK"
    return {
        **base,
        "status": status,
        "n_per_30s": n,
        "fastest_interval": 30 / n,
        "recommended_interval": 30 / (n * MARGIN),
    }
