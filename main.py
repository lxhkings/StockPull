"""StockPull CLI: prices | tushare | futu | init | status | db"""

from __future__ import annotations

import logging
import os
import sys

from cli.deprecate import rewrite_legacy_argv
from cli.parser import build_parser

# Re-export cmd_* / helpers so tests can `from main import ...` and patch("main.cmd_*")
from cli.commands_common import _format_run_result  # noqa: F401
from cli.commands_meta import cmd_init, cmd_status
from cli.commands_prices import cmd_daily, cmd_weekly, cmd_rebase, cmd_intraday
from cli.commands_tushare import cmd_tushare_backfill, cmd_tushare_full, cmd_tushare_flush
from cli.commands_futu import cmd_futu_full, cmd_futu_sync, cmd_futu_flush
from cli.commands_db import cmd_migrate_intraday, cmd_purge_index

# Optional NO_PROXY for eastmoney/xueqiu hosts (legacy; primary feeds are
# tushare/yfinance/futu). Do not set NO_PROXY=* — yfinance may need system proxy.
_AKSHARE_NO_PROXY = "eastmoney.com,*.eastmoney.com,xueqiu.com,*.xueqiu.com"
existing = os.environ.get("NO_PROXY", "")
os.environ["NO_PROXY"] = ",".join(filter(None, [existing, _AKSHARE_NO_PROXY]))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger(__name__)

MARKETS = ("us", "cn", "hk", "all")


def _dispatch_prices(args) -> int:
    c = args.prices_cmd
    if c == "daily":
        return cmd_daily(args.market, args.code, args.index)
    if c == "weekly":
        return cmd_weekly(args.market, args.code)
    if c == "intraday":
        return cmd_intraday(args.interval, args.rebase)
    if c == "rebase":
        return cmd_rebase(args.market, args.code, args.years, args.index, args.etf_only)
    return 1


def _dispatch_tushare(args) -> int:
    c = args.tushare_cmd
    if c == "sync":
        return cmd_tushare_backfill(
            args.scope, args.market, args.dry_run, getattr(args, "start", None),
        )
    if c == "full":
        return cmd_tushare_full(args.scope, args.market, args.dry_run)
    if c == "flush":
        return cmd_tushare_flush(args.workers)
    return 1


def _dispatch_futu(args) -> int:
    c = args.futu_cmd
    if c == "sync":
        return cmd_futu_sync(args.scope)
    if c == "full":
        return cmd_futu_full(args.scope)
    if c == "flush":
        return cmd_futu_flush()
    return 1


def _dispatch_db(args) -> int:
    if args.db_cmd == "migrate-intraday":
        return cmd_migrate_intraday()
    if args.db_cmd == "purge-index":
        return cmd_purge_index(args.index_id, yes=args.yes)
    return 1


def main(argv: list[str] | None = None) -> int:
    # None → sys.argv[1:] so subprocess / `python main.py daily` also rewrite
    raw = list(argv) if argv is not None else sys.argv[1:]
    args = build_parser().parse_args(rewrite_legacy_argv(raw))
    if args.cmd == "prices":
        return _dispatch_prices(args)
    if args.cmd == "tushare":
        return _dispatch_tushare(args)
    if args.cmd == "futu":
        return _dispatch_futu(args)
    if args.cmd == "db":
        return _dispatch_db(args)
    if args.cmd == "init":
        return cmd_init()
    if args.cmd == "status":
        return cmd_status()
    return 1


if __name__ == "__main__":
    sys.exit(main())
