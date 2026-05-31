#!/usr/bin/env python3
"""验证 Futu 18 个未实现接口的返回结构。分组测试，每组限 3 个。"""
import json
import sys
import time
from pprint import pprint

from futu import OpenQuoteContext

HOST, PORT = "127.0.0.1", 11111
CODE = "US.AAPL"
CODES = [CODE]


def section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def show(name, ret, data):
    print(f"\n--- {name} (ret={ret}) ---")
    if ret != 0:
        print(f"  ERROR: {data}")
        return
    if data is None:
        print("  None")
    elif hasattr(data, "to_dict"):
        print(f"  DataFrame shape={data.shape}, cols={list(data.columns)[:10]}...")
        if len(data) > 0:
            for col in list(data.columns)[:8]:
                print(f"    {col}: {repr(data.iloc[0][col])[:80]}")
    elif isinstance(data, dict):
        print(f"  dict keys={list(data.keys())}")
        # show first 2 levels
        for k, v in data.items():
            if isinstance(v, list) and len(v) > 0:
                print(f"  {k}[0]: {repr(v[0])[:120]}")
            elif isinstance(v, dict):
                print(f"  {k}.keys={list(v.keys())[:5]}")
            else:
                print(f"  {k}: {repr(v)[:80]}")
    else:
        print(f"  {type(data).__name__}: {repr(data)[:120]}")


def main():
    group = sys.argv[1] if len(sys.argv) > 1 else "all"
    ctx = OpenQuoteContext(host=HOST, port=PORT)

    try:
        if group in ("all", "meta"):
            section("元数据")
            r, d = ctx.get_company_profile(CODES)
            show("get_company_profile(list)", r, d)

        if group in ("all", "fin_ext"):
            section("财报补充")
            r, d = ctx.get_financials_revenue_breakdown(CODE)
            show("get_financials_revenue_breakdown", r, d)
            time.sleep(1)
            r, d = ctx.get_financials_earnings_price_move(CODE)
            show("get_financials_earnings_price_move", r, d)

        if group in ("all", "val"):
            section("估值 + 分析师")
            r, d = ctx.get_valuation_detail(CODES)
            show("get_valuation_detail(list)", r, d)
            time.sleep(1)
            r, d = ctx.get_research_rating_summary(CODE)
            show("get_research_rating_summary", r, d)
            time.sleep(1)
            r, d = ctx.get_research_morningstar_report(CODE)
            show("get_research_morningstar_report", r, d)

        if group in ("all", "holder"):
            section("股东/筹码")
            r, d = ctx.get_shareholders_overview(CODE)
            show("get_shareholders_overview", r, d)
            time.sleep(1)
            r, d = ctx.get_shareholders_holding_changes(CODE)
            show("get_shareholders_holding_changes", r, d)
            time.sleep(1)
            r, d = ctx.get_shareholders_institutional(CODE)
            show("get_shareholders_institutional", r, d)

        if group in ("all", "insider"):
            section("内部人")
            r, d = ctx.get_insider_holders_list(CODE)
            show("get_insider_holders_list", r, d)
            time.sleep(1)
            r, d = ctx.get_insider_trade_list(CODE)
            show("get_insider_trade_list", r, d)

        if group in ("all", "flow"):
            section("资金流/卖空")
            r, d = ctx.get_capital_flow(CODES)
            show("get_capital_flow(list)", r, d)
            time.sleep(1)
            r, d = ctx.get_capital_distribution(CODES)
            show("get_capital_distribution(list)", r, d)
            time.sleep(1)
            r, d = ctx.get_short_interest(CODES)
            show("get_short_interest(list)", r, d)
            time.sleep(1)
            r, d = ctx.get_daily_short_volume(CODES)
            show("get_daily_short_volume(list)", r, d)

        if group in ("all", "quality"):
            section("公司质量")
            r, d = ctx.get_company_operational_efficiency(CODES)
            show("get_company_operational_efficiency(list)", r, d)

        if group in ("all", "option"):
            section("期权")
            r, d = ctx.get_option_chain(CODE)
            show("get_option_chain", r, d)
            time.sleep(1)
            r, d = ctx.get_option_volatility(CODE)
            show("get_option_volatility", r, d)

    finally:
        ctx.close()


if __name__ == "__main__":
    main()
