"""Price pipeline CLI commands: daily, weekly, rebase, intraday."""

from __future__ import annotations

import logging
import sys

from cli.commands_common import _import_market

log = logging.getLogger(__name__)


def cmd_daily(market: str, codes: list[str] | None, index: str | None) -> int:
    from jobs.pipeline import Pipeline
    targets = ["us", "cn", "hk"] if market == "all" else [market]
    for m in targets:
        mod = _import_market(m)
        if codes:
            # Single-ticker debug path: skip Step 1/2, run incremental on the codes only
            print(f"[{m}] daily --code {codes}: running incremental only")
            mod.incremental(codes)
        else:
            # 只对 US 市场传递 index 参数
            pipe_index = index if m == "us" else None
            Pipeline(mod).daily(index=pipe_index)
    return 0


def cmd_weekly(market: str, codes: list[str] | None) -> int:
    mod = _import_market(market)
    result = mod.weekly(codes)
    ok = sum(1 for v in result.values() if v == "ok")
    print(f"[{market}] weekly done: {ok}/{len(result)} ok")
    return 0


def cmd_rebase(market: str, codes: list[str] | None, years: int | None, index: str | None, etf_only: bool = False) -> int:
    if etf_only:
        if market != "cn":
            print("--etf-only currently only supports --market cn", file=sys.stderr)
            return 1
        mod = _import_market("cn")
        n = mod.rebase_etf(full_rebase=True)
        print(f"[cn] ETF rebase wrote {n} rows to index_prices")
        return 0

    mod = _import_market(market)
    targets = codes or mod.list_active_tickers(index=index)

    years_msg = f" ({years} 年)" if years else ""
    index_msg = f" [{index}]" if index else ""
    print(f"[{market}] rebase {len(targets)} tickers{index_msg}{years_msg} (full history)")

    mod.rebase(targets, years=years, index=index)

    return 0


def cmd_intraday(interval: str | None, rebase: bool = False) -> int:
    from apis.yfinance.prices_intraday import SUPPORTED_INTERVALS
    mod = _import_market("us")
    intervals = [interval] if interval else None
    log.info(
        f"[intraday] 开始拉取 "
        f"{intervals or SUPPORTED_INTERVALS}"
        + (" (rebase)" if rebase else "")
    )
    result = mod.intraday(intervals=intervals, full_rebase=rebase)
    ok = sum(1 for v in result.values() if v == "ok")
    err = sum(1 for v in result.values() if v.startswith("error"))
    log.info(f"[intraday] 完成: ok={ok}, error={err}")
    return 0
