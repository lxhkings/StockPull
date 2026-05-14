"""Project_B CLI entry. Subcommands: init / daily / rebase / status."""

from __future__ import annotations

import argparse
import logging
import os
import sys

# Bypass all proxy settings (including macOS system proxy) to avoid connection issues
# Must happen before any library imports that use requests/urllib3
_PROXY_KEYS = [
    "HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy",
    "ALL_PROXY", "all_proxy",
]
for _key in _PROXY_KEYS:
    os.environ.pop(_key, None)
os.environ["NO_PROXY"] = "*"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

MARKETS = ("us", "cn", "hk", "all")


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="main.py", description="Unified ingest for US/CN/HK")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="Insert CSI800/HSI rows into indices table (idempotent)")

    p_daily = sub.add_parser("daily", help="Run incremental daily ingest")
    p_daily.add_argument("--market", choices=MARKETS, default="all")
    p_daily.add_argument("--code", action="append", default=None,
                         help="Only this ticker (repeatable, debug aid)")
    p_daily.add_argument("--index", default=None,
                         help="指数成分股（仅 US 市场：SP500）")

    p_rebase = sub.add_parser("rebase", help="Full re-pull (qfq drift fix)")
    p_rebase.add_argument("--market", choices=("cn", "hk", "us"), required=True)
    p_rebase.add_argument("--code", action="append", default=None)
    p_rebase.add_argument("--years", type=int, default=None, help="历史年数（默认：US=5, CN/HK=15）")
    p_rebase.add_argument("--index", default=None,
                          help="指数成分股（仅 US 市场：SP500）")

    sub.add_parser("status", help="Print ingest status summary")

    p_ts = sub.add_parser("tushare-backfill", help="Tushare 一次性回填三市场底层数据")
    p_ts.add_argument("--scope", choices=("all", "lists", "prices", "derive", "financial"),
                      default="all")
    p_ts.add_argument("--market", choices=("all", "cn", "hk", "us"), default="all")
    p_ts.add_argument("--dry-run", action="store_true")

    return p


def cmd_init() -> int:
    from db import execute
    from config import INDEX_CONFIG
    rows = [
        (idx, cfg["name"], cfg["etf"], cfg["description"])
        for idx, cfg in INDEX_CONFIG.items()
    ]
    n = execute(
        "INSERT IGNORE INTO indices (index_id, name, etf_ticker, description) "
        "VALUES (%s,%s,%s,%s)",
        rows, many=True,
    )
    print(f"init: inserted {n} new rows into `indices` (existing rows unchanged)")
    return 0


def cmd_status() -> int:
    from db import show_status
    show_status()
    return 0


def cmd_daily(market: str, codes: list[str] | None, index: str | None) -> int:
    from data.pipeline import Pipeline
    targets = ["us", "cn", "hk"] if market == "all" else [market]
    for m in targets:
        try:
            mod = _import_market(m)
        except ImportError as e:
            print(f"[{m}] not yet implemented: {e}", file=sys.stderr)
            continue

        if codes:
            # Single-ticker debug path: skip Step 1/2, run incremental on the codes only
            print(f"[{m}] daily --code {codes}: running incremental only")
            mod.incremental(codes)
        else:
            # 只对 US 市场传递 index 参数
            pipe_index = index if m == "us" else None
            Pipeline(mod).daily(index=pipe_index)
    return 0


def cmd_rebase(market: str, codes: list[str] | None, years: int | None, index: str | None) -> int:
    import inspect
    mod = _import_market(market)
    if not hasattr(mod, "rebase"):
        print(f"[{market}] rebase not implemented", file=sys.stderr)
        return 1

    # US 模块支持 index 参数，CN/HK 不支持（使用 inspect 判断）
    sig_list = inspect.signature(mod.list_active_tickers)
    if 'index' in sig_list.parameters:
        targets = codes or mod.list_active_tickers(index=index)
    else:
        targets = codes or mod.list_active_tickers()

    years_msg = f" ({years} 年)" if years else ""
    index_msg = f" [{index}]" if index else ""
    print(f"[{market}] rebase {len(targets)} tickers{index_msg}{years_msg} (full history)")

    # rebase 函数同样检查 index 参数
    sig_rebase = inspect.signature(mod.rebase)
    if 'index' in sig_rebase.parameters:
        mod.rebase(targets, years=years, index=index)
    else:
        mod.rebase(targets, years=years)

    return 0


def cmd_tushare_backfill(scope: str, market: str, dry_run: bool) -> int:
    from ts_ingest.orchestrator import run_full_backfill
    rep = run_full_backfill(scope=scope, market=market, dry_run=dry_run)
    print(rep.render())
    return 0


def _import_market(market: str):
    if market == "us":
        from data import market_us as m
    elif market == "cn":
        from data import market_cn as m
    elif market == "hk":
        from data import market_hk as m
    else:
        raise ValueError(market)
    return m


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.cmd == "init":
        return cmd_init()
    if args.cmd == "status":
        return cmd_status()
    if args.cmd == "daily":
        return cmd_daily(args.market, args.code, args.index)
    if args.cmd == "rebase":
        return cmd_rebase(args.market, args.code, args.years, args.index)
    if args.cmd == "tushare-backfill":
        return cmd_tushare_backfill(args.scope, args.market, args.dry_run)
    return 1


if __name__ == "__main__":
    sys.exit(main())
