"""Project_B CLI entry. Subcommands: init / daily / rebase / status."""

from __future__ import annotations

import argparse
import logging
import sys

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

    p_rebase = sub.add_parser("rebase", help="Full re-pull (hfq drift fix)")
    p_rebase.add_argument("--market", choices=("cn", "hk"), required=True)
    p_rebase.add_argument("--code", action="append", default=None)

    sub.add_parser("status", help="Print ingest status summary")

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


def cmd_daily(market: str, codes: list[str] | None) -> int:
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
            Pipeline(mod).daily()
    return 0


def cmd_rebase(market: str, codes: list[str] | None) -> int:
    mod = _import_market(market)
    if not hasattr(mod, "rebase"):
        print(f"[{market}] rebase not implemented", file=sys.stderr)
        return 1
    targets = codes or mod.list_active_tickers()
    print(f"[{market}] rebase {len(targets)} tickers (full history)")
    mod.rebase(targets)
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
        return cmd_daily(args.market, args.code)
    if args.cmd == "rebase":
        return cmd_rebase(args.market, args.code)
    return 1


if __name__ == "__main__":
    sys.exit(main())
