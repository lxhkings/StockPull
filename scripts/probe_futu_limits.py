#!/usr/bin/env python3
"""一次性探测 Futu quote/F10 接口限频(n 次/30s)。突发计数法。

用法:
    uv run python scripts/probe_futu_limits.py            # 全量 21 接口
    uv run python scripts/probe_futu_limits.py --only get_company_profile  # 单接口(冒烟)
前置:OpenD 已启动登录于 127.0.0.1:11111;勿与生产 backfill 并行。
"""
from __future__ import annotations

import argparse
import json
import socket
import time
from datetime import date
from pathlib import Path

# ── 常量 ──
RET_OK = 0
FREQ_PATTERNS = (
    "频率", "限频", "frequent", "frequency", "too many", "rate limit", "请求过于",
)
CAP = 120          # burst 安全上限
MARGIN = 0.8       # 推荐速率留 20% 余量
HOST, PORT = "127.0.0.1", 11111
CODE = "US.AAPL"
NUM = 50
RESET_SLEEP = 35   # > 30s 滑动窗口,确保重置
ROUNDS = 3
OUT_DIR = Path("docs/superpowers/probe-results")


# ── 纯函数 ──

def classify(ret: int, data) -> str:
    """归类单次调用结果:OK / FREQ / OTHER。"""
    if ret == RET_OK:
        return "OK"
    msg = str(data).lower()
    if any(p.lower() in msg for p in FREQ_PATTERNS):
        return "FREQ"
    return "OTHER"


def summarize_rounds(interface: str, rounds: list[int], raw_msg: str) -> dict:
    """聚合某接口多轮 burst 结果。rounds 含 -1 → SKIP;min ≥ CAP → NO-LIMIT;否则取 min。"""
    base = {"interface": interface, "raw_msg": raw_msg}
    if any(n < 0 for n in rounds):
        return {**base, "status": "SKIP", "n_per_30s": None,
                "fastest_interval": None, "recommended_interval": None}
    n = min(rounds)
    if n == 0:
        return {**base, "status": "FREQ@0", "n_per_30s": 0,
                "fastest_interval": None, "recommended_interval": None}
    status = "NO-LIMIT@cap" if n >= CAP else "OK"
    return {
        **base,
        "status": status,
        "n_per_30s": n,
        "fastest_interval": 30 / n,
        "recommended_interval": 30 / (n * MARGIN),
    }


# ── 探测逻辑 ──

def _build_probes(ctx):
    """返回 [(name, callable_returning_(ret,data)), ...]。"""
    from futu import PeriodType
    return [
        ("get_market_snapshot",                  lambda: ctx.get_market_snapshot([CODE])),
        ("get_company_profile",                  lambda: ctx.get_company_profile(CODE)),
        ("get_financials_revenue_breakdown",     lambda: ctx.get_financials_revenue_breakdown(CODE)),
        ("get_financials_earnings_price_history", lambda: ctx.get_financials_earnings_price_history(CODE)),
        ("get_financials_earnings_price_move",   lambda: ctx.get_financials_earnings_price_move(CODE)),
        ("get_company_operational_efficiency",   lambda: ctx.get_company_operational_efficiency(CODE)),
        ("get_corporate_actions_dividends",      lambda: ctx.get_corporate_actions_dividends(CODE)),
        ("get_corporate_actions_stock_splits",   lambda: ctx.get_corporate_actions_stock_splits(CODE, next_key=None, num=NUM)),
        ("get_insider_holder_list",              lambda: ctx.get_insider_holder_list(CODE)),
        ("get_insider_trade_list",               lambda: ctx.get_insider_trade_list(CODE)),
        ("get_shareholders_overview",            lambda: ctx.get_shareholders_overview(CODE)),
        ("get_shareholders_institutional",       lambda: ctx.get_shareholders_institutional(CODE)),
        ("get_shareholders_holding_changes",     lambda: ctx.get_shareholders_holding_changes(CODE)),
        ("get_research_analyst_consensus",       lambda: ctx.get_research_analyst_consensus(CODE)),
        ("get_research_rating_summary",          lambda: ctx.get_research_rating_summary(CODE, num=NUM)),
        ("get_research_morningstar_report",      lambda: ctx.get_research_morningstar_report(CODE)),
        ("get_valuation_detail",                 lambda: ctx.get_valuation_detail(CODE)),
        ("get_capital_flow",                     lambda: ctx.get_capital_flow(CODE, period_type=PeriodType.DAY)),
        ("get_capital_distribution",             lambda: ctx.get_capital_distribution(CODE)),
        ("get_short_interest",                   lambda: ctx.get_short_interest(CODE, next_key=None, num=NUM)),
        ("get_daily_short_volume",               lambda: ctx.get_daily_short_volume(CODE, next_key=None, num=NUM)),
    ]


def _unpack(result):
    """futu 返回 2 值或 3 值(short_interest/daily_short_volume)。统一成 (ret, data)。"""
    if isinstance(result, tuple) and len(result) == 3:
        return result[0], result[1]
    return result


def burst_probe(make_call, cap: int = CAP) -> tuple[int, str]:
    """紧循环调用直到首次 FREQ。返回 (成功次数, message)。
    OTHER → (-1, msg);达到 cap → (cap, 'no-limit-hit@cap')。"""
    ok = 0
    for _ in range(cap):
        ret, data = _unpack(make_call())
        kind = classify(ret, data)
        if kind == "OK":
            ok += 1
            continue
        if kind == "FREQ":
            return ok, str(data)
        return -1, str(data)   # OTHER:不可测
    return cap, "no-limit-hit@cap"


def probe_one(name: str, make_call) -> dict:
    """3 轮 burst,轮间 sleep RESET_SLEEP。任一轮 OTHER 即 SKIP。"""
    rounds, raw_msg = [], ""
    for i in range(ROUNDS):
        n, msg = burst_probe(make_call)
        rounds.append(n)
        raw_msg = msg
        print(f"  [{name}] round {i+1}/{ROUNDS}: n={n}  msg={msg[:60]!r}")
        if n < 0:
            break   # OTHER 无需重复
        if i < ROUNDS - 1:
            print(f"    sleep {RESET_SLEEP}s 重置窗口...")
            time.sleep(RESET_SLEEP)
    return summarize_rounds(name, rounds, raw_msg)


# ── 输出 ──

def print_table(results: list[dict]) -> None:
    print(f"\n{'interface':<38} {'n/30s':>6} {'fastest':>8} {'recommend':>10} {'status':<13} raw_msg")
    print("-" * 100)
    for r in results:
        n = "-" if r["n_per_30s"] is None else r["n_per_30s"]
        fi = "-" if r["fastest_interval"] is None else f"{r['fastest_interval']:.3f}"
        ri = "-" if r["recommended_interval"] is None else f"{r['recommended_interval']:.3f}"
        print(f"{r['interface']:<38} {str(n):>6} {fi:>8} {ri:>10} {r['status']:<13} {r['raw_msg'][:40]!r}")


def write_json(results: list[dict]) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"{date.today().isoformat()}-futu-limits.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2))
    return out


def _check_opend(host: str, port: int) -> None:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(2)
    try:
        s.connect((host, port))
    except OSError as e:
        raise SystemExit(f"无法连接 OpenD ({host}:{port}): {e}。请先启动 OpenD。")
    finally:
        s.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="只测单个接口名(冒烟用)")
    args = ap.parse_args()

    _check_opend(HOST, PORT)
    from futu import OpenQuoteContext
    ctx = OpenQuoteContext(host=HOST, port=PORT)
    try:
        probes = _build_probes(ctx)
        if args.only:
            probes = [(n, fn) for n, fn in probes if n == args.only]
            if not probes:
                raise SystemExit(f"未知接口: {args.only}")
        results = []
        for name, fn in probes:
            print(f"\n=== probing {name} ===")
            results.append(probe_one(name, fn))
        print_table(results)
        out = write_json(results)
        print(f"\n写入 {out}")
    finally:
        ctx.close()


if __name__ == "__main__":
    main()
