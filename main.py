"""StockPull CLI: prices | tushare | futu | init | status | db"""

from __future__ import annotations

import logging
import os
import sys

from cli.deprecate import warn_deprecated
from cli.parser import build_parser

# akshare/efinance (eastmoney.com) must bypass proxy — direct connect only.
# yfinance (Yahoo Finance) should still go through proxy to avoid rate limits.
# So we only add eastmoney domains to NO_PROXY, not "*".
_AKSHARE_NO_PROXY = "eastmoney.com,*.eastmoney.com,xueqiu.com,*.xueqiu.com"
existing = os.environ.get("NO_PROXY", "")
os.environ["NO_PROXY"] = ",".join(filter(None, [existing, _AKSHARE_NO_PROXY]))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger(__name__)

MARKETS = ("us", "cn", "hk", "all")


def cmd_init() -> int:
    from core.db_client import execute
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
    from modules.db_admin import show_status
    show_status()
    return 0


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
        from apis.tushare.etf_cn import update_etf_prices
        n = update_etf_prices(full_rebase=True)
        print(f"[cn] ETF rebase wrote {n} rows to index_prices")
        return 0

    mod = _import_market(market)
    targets = codes or mod.list_active_tickers(index=index)

    years_msg = f" ({years} 年)" if years else ""
    index_msg = f" [{index}]" if index else ""
    print(f"[{market}] rebase {len(targets)} tickers{index_msg}{years_msg} (full history)")

    mod.rebase(targets, years=years, index=index)

    return 0


def cmd_migrate_intraday() -> int:
    from modules.db_admin import create_prices_intraday_table
    create_prices_intraday_table()
    print("prices_intraday table ready")
    return 0


def cmd_purge_index(index_id: str, yes: bool = False) -> int:
    """清理某 index_id 在指数相关表中的行。默认 dry-run，--yes 才 DELETE。"""
    from modules.db_admin import purge_index

    if not yes:
        counts = purge_index(index_id, dry_run=True)
        total = sum(counts.values())
        print(f"[dry-run] index_id={index_id!r} 各表行数（合计 {total}）：")
        for table, n in counts.items():
            print(f"  {table}: {n}")
        if total == 0:
            print("无数据，无需清理。")
        else:
            print(f"确认删除请加 --yes：uv run main.py db purge-index --index-id {index_id} --yes")
        return 0

    deleted = purge_index(index_id, dry_run=False)
    total = sum(deleted.values())
    print(f"[deleted] index_id={index_id!r} 合计 {total} 行：")
    for table, n in deleted.items():
        print(f"  {table}: {n}")
    return 0


def cmd_intraday(interval: str | None, rebase: bool = False) -> int:
    from jobs import market_us
    from apis.yfinance.prices_intraday import SUPPORTED_INTERVALS
    intervals = [interval] if interval else None  # None → market_us 用 SUPPORTED_INTERVALS
    log.info(
        f"[intraday] 开始拉取 "
        f"{intervals or SUPPORTED_INTERVALS}"
        + (" (rebase)" if rebase else "")
    )
    result = market_us.intraday(intervals=intervals, full_rebase=rebase)
    ok = sum(1 for v in result.values() if v == "ok")
    err = sum(1 for v in result.values() if v.startswith("error"))
    log.info(f"[intraday] 完成: ok={ok}, error={err}")
    return 0


def cmd_tushare_backfill(scope: str, market: str, dry_run: bool, start: str | None = None) -> int:
    """两阶段：backfill 写本地缓冲 → 自动 flush 到 NAS。flush 失败则保留缓冲、提示兜底。"""
    from core.db_client import set_local_first
    from apis.tushare.orchestrator import run_full_backfill
    from core.local_buffer import flush, pending_count
    from config import TUSHARE_BUFFER_PATH

    if dry_run:
        # 预检不写数据，不需要走本地缓冲
        rep = run_full_backfill(scope=scope, market=market, dry_run=dry_run, start=start)
        print(rep.render())
        return 0

    set_local_first(True, buffer_path=TUSHARE_BUFFER_PATH)
    try:
        rep = run_full_backfill(scope=scope, market=market, dry_run=dry_run, start=start)
    finally:
        set_local_first(False)
    print(rep.render())

    try:
        fstat = flush(TUSHARE_BUFFER_PATH)
        print(f"flush -> NAS: {fstat}")
    except Exception as e:  # noqa: BLE001
        n = pending_count(TUSHARE_BUFFER_PATH)
        print(f"BACKFILL 完成并已存本地。FLUSH 失败: {e}\n"
              f"缓冲 {n} 条待传保留。NAS 恢复后跑: uv run main.py tushare flush")
        return 1
    return 0


def cmd_tushare_full(scope: str, market: str, dry_run: bool) -> int:
    """全量强制回填：起点固定为 TUSHARE_BACKFILL_START，等价 tushare-backfill --start 2010起。"""
    from config import TUSHARE_BACKFILL_START
    return cmd_tushare_backfill(scope, market, dry_run, start=TUSHARE_BACKFILL_START)


def cmd_tushare_sync(scope: str, market: str, dry_run: bool) -> int:
    """增量拉取：不传 start，各 domain 走自己的默认行为（能增量的增量，financial/dividend 接口限制仍全量）。"""
    return cmd_tushare_backfill(scope, market, dry_run, start=None)


def cmd_tushare_flush(workers: int = 1) -> int:
    from core.local_buffer import flush, flush_parallel, pending_count
    from config import TUSHARE_BUFFER_PATH
    n = pending_count(TUSHARE_BUFFER_PATH)
    if n == 0:
        print("无待传数据。")
        return 0
    if workers > 1:
        print(f"待传 {n} 条，开始 flush -> NAS (并发 {workers}) ...")
        print(flush_parallel(TUSHARE_BUFFER_PATH, workers=workers))
    else:
        print(f"待传 {n} 条，开始 flush -> NAS ...")
        print(flush(TUSHARE_BUFFER_PATH))
    return 0


def _run_futu(scope: str, force: bool) -> int:
    """两阶段：fetch 写本地缓冲 → 自动 flush 到 NAS。flush 失败则保留缓冲、提示兜底。"""
    from core.db_client import set_local_first
    from apis.futu.orchestrator import run_sync
    from core.local_buffer import flush, pending_count
    from config import FUTU_BUFFER_PATH

    set_local_first(True)
    try:
        rep = run_sync(scope=scope, force=force)
    finally:
        set_local_first(False)
    print(rep)

    try:
        fstat = flush(FUTU_BUFFER_PATH)
        print(f"flush -> NAS: {fstat}")
    except Exception as e:  # noqa: BLE001
        n = pending_count(FUTU_BUFFER_PATH)
        print(f"FETCH 完成并已存本地。FLUSH 失败: {e}\n"
              f"缓冲 {n} 条待传保留。NAS 恢复后跑: uv run main.py futu flush")
        return 1
    return 0


def cmd_futu_full(scope: str) -> int:
    return _run_futu(scope, force=True)


def cmd_futu_sync(scope: str) -> int:
    return _run_futu(scope, force=False)


def cmd_futu_flush() -> int:
    from core.local_buffer import flush, pending_count
    from config import FUTU_BUFFER_PATH
    n = pending_count(FUTU_BUFFER_PATH)
    if n == 0:
        print("无待传数据。")
        return 0
    print(f"待传 {n} 条，开始 flush -> NAS ...")
    print(flush(FUTU_BUFFER_PATH))
    return 0


def _import_market(market: str):
    if market == "us":
        from jobs import market_us as m
    elif market == "cn":
        from jobs import market_cn as m
    elif market == "hk":
        from jobs import market_hk as m
    else:
        raise ValueError(market)
    return m


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
    args = build_parser().parse_args(argv)
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
    # Legacy top-level — warn then forward to existing cmd_*
    if args.cmd == "daily":
        warn_deprecated("daily", "prices daily")
        return cmd_daily(args.market, args.code, args.index)
    if args.cmd == "weekly":
        warn_deprecated("weekly", "prices weekly")
        return cmd_weekly(args.market, args.code)
    if args.cmd == "intraday":
        warn_deprecated("intraday", "prices intraday")
        return cmd_intraday(args.interval, args.rebase)
    if args.cmd == "rebase":
        warn_deprecated("rebase", "prices rebase")
        return cmd_rebase(args.market, args.code, args.years, args.index, args.etf_only)
    if args.cmd == "tushare-sync":
        warn_deprecated("tushare-sync", "tushare sync")
        return cmd_tushare_sync(args.scope, args.market, args.dry_run)
    if args.cmd == "tushare-full":
        warn_deprecated("tushare-full", "tushare full")
        return cmd_tushare_full(args.scope, args.market, args.dry_run)
    if args.cmd == "tushare-backfill":
        warn_deprecated("tushare-backfill", "tushare sync")
        return cmd_tushare_backfill(args.scope, args.market, args.dry_run, args.start)
    if args.cmd == "tushare-flush":
        warn_deprecated("tushare-flush", "tushare flush")
        return cmd_tushare_flush(args.workers)
    if args.cmd == "futu-sync":
        warn_deprecated("futu-sync", "futu sync")
        return cmd_futu_sync(args.scope)
    if args.cmd == "futu-full":
        warn_deprecated("futu-full", "futu full")
        return cmd_futu_full(args.scope)
    if args.cmd == "futu-flush":
        warn_deprecated("futu-flush", "futu flush")
        return cmd_futu_flush()
    if args.cmd == "migrate-intraday":
        warn_deprecated("migrate-intraday", "db migrate-intraday")
        return cmd_migrate_intraday()
    return 1


if __name__ == "__main__":
    sys.exit(main())
