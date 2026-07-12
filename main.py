"""StockPull CLI: prices | tushare | futu | init | status | db"""

from __future__ import annotations

import logging
import os
import sys
from collections.abc import Callable
from typing import Any

from cli.deprecate import rewrite_legacy_argv
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


def _format_run_result(result: Any) -> str:
    render = getattr(result, "render", None)
    if callable(render):
        return render()
    return str(result)


def _run_buffered(
    buffer_path: str,
    run_fn: Callable[[], Any],
    *,
    done_label: str,
    flush_cmd: str,
) -> int:
    """本地缓冲两阶段：set_local_first → run_fn → flush。flush 失败保留缓冲。"""
    from core.db_client import set_local_first
    from core.local_buffer import flush, pending_count

    set_local_first(True, buffer_path=buffer_path)
    try:
        result = run_fn()
    finally:
        set_local_first(False)

    print(_format_run_result(result))

    try:
        fstat = flush(buffer_path)
        print(f"flush -> NAS: {fstat}")
    except Exception as e:  # noqa: BLE001
        n = pending_count(buffer_path)
        print(
            f"{done_label}完成并已存本地。FLUSH 失败: {e}\n"
            f"缓冲 {n} 条待传保留。NAS 恢复后跑: uv run main.py {flush_cmd}"
        )
        return 1
    return 0


def cmd_tushare_backfill(scope: str, market: str, dry_run: bool, start: str | None = None) -> int:
    """两阶段：backfill 写本地缓冲 → 自动 flush 到 NAS。flush 失败则保留缓冲、提示兜底。"""
    from apis.tushare.orchestrator import run_full_backfill
    from config import TUSHARE_BUFFER_PATH

    if dry_run:
        rep = run_full_backfill(scope=scope, market=market, dry_run=dry_run, start=start)
        print(rep.render())
        return 0

    return _run_buffered(
        TUSHARE_BUFFER_PATH,
        lambda: run_full_backfill(scope=scope, market=market, dry_run=False, start=start),
        done_label="BACKFILL ",
        flush_cmd="tushare flush",
    )


def cmd_tushare_full(scope: str, market: str, dry_run: bool) -> int:
    """全量强制回填：起点固定为 TUSHARE_BACKFILL_START，等价 tushare sync --start 2010起。"""
    from config import TUSHARE_BACKFILL_START
    return cmd_tushare_backfill(scope, market, dry_run, start=TUSHARE_BACKFILL_START)


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
    from apis.futu.orchestrator import run_sync
    from config import FUTU_BUFFER_PATH

    return _run_buffered(
        FUTU_BUFFER_PATH,
        lambda: run_sync(scope=scope, force=force),
        done_label="FETCH ",
        flush_cmd="futu flush",
    )


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
