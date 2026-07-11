"""Project_B CLI entry. Subcommands: init / daily / rebase / status."""

from __future__ import annotations

import argparse
import logging
import os
import sys

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
    p_rebase.add_argument("--etf-only", action="store_true",
                          help="仅重灌 ETF index_prices（仅 CN 市场）")

    p_weekly = sub.add_parser("weekly", help="Run weekly ingest (US/CN market)")
    p_weekly.add_argument("--market", choices=("us", "cn"), default="us")
    p_weekly.add_argument("--code", action="append", default=None,
                          help="Only this ticker (repeatable, debug aid)")

    sub.add_parser("status", help="Print ingest status summary")

    sub.add_parser("migrate-intraday", help="Create prices_intraday table (idempotent)")

    p_intraday = sub.add_parser("intraday", help="拉取美股分钟级行情（15m / 1h）并写入 prices_intraday")
    p_intraday.add_argument(
        "--interval",
        choices=["15m", "1h"],
        default=None,
        help="仅拉取指定 interval（默认：15m 和 1h 均拉）",
    )
    p_intraday.add_argument(
        "--rebase",
        action="store_true",
        default=False,
        help="全量回补，忽略 sync_log，拉满最大可得历史（1h=730天，15m=60天）",
    )

    _TS_SCOPES = ("all", "lists", "prices", "derive", "financial", "valuation", "shareholder_return")

    p_ts = sub.add_parser("tushare-backfill", help="Tushare 回填（--start 自定义起点，需要精细控制时用）")
    p_ts.add_argument("--scope", choices=_TS_SCOPES, default="all")
    p_ts.add_argument("--market", choices=("all", "cn", "hk", "us"), default="all")
    p_ts.add_argument("--dry-run", action="store_true")
    p_ts.add_argument("--start", default=None,
                      help="YYYYMMDD，强制指定起点重新回填历史（valuation 默认从上次同步点增量续拉，"
                           "需要这个才会往回填；financial 默认已是 TUSHARE_BACKFILL_START 全量，"
                           "传了就换成这个起点）")

    p_tfull = sub.add_parser("tushare-full", help="Tushare 全量强制回填（=tushare-backfill --start 2010起；"
                                                   "financial/dividend 接口本来就每次全量，无实际差异）")
    p_tfull.add_argument("--scope", choices=_TS_SCOPES, default="all")
    p_tfull.add_argument("--market", choices=("all", "cn", "hk", "us"), default="all")
    p_tfull.add_argument("--dry-run", action="store_true")

    p_tsync = sub.add_parser("tushare-sync", help="Tushare 增量拉取（=tushare-backfill 不带 --start；"
                                                    "valuation/repurchase/holdertrade 从上次同步点续拉，"
                                                    "financial/dividend 接口限制仍是全量）")
    p_tsync.add_argument("--scope", choices=_TS_SCOPES, default="all")
    p_tsync.add_argument("--market", choices=("all", "cn", "hk", "us"), default="all")
    p_tsync.add_argument("--dry-run", action="store_true")

    SCOPES = ("all", "other", "daily", "weekly", "financial", "earnings", "actions",
              "profile", "revenue", "shareholders", "efficiency")
    p_ff = sub.add_parser("futu-full", help="Futu 全量采集（忽略节流，强制重拉）")
    p_ff.add_argument("--scope", choices=SCOPES, default="all")
    p_fs = sub.add_parser("futu-sync", help="Futu 增量采集（按接口频率节流，cron 每日跑）")
    p_fs.add_argument("--scope", choices=SCOPES, default="all")
    sub.add_parser("futu-flush", help="把本地缓冲重放到 NAS（futu-full/sync flush 失败后兜底）")
    p_tf = sub.add_parser("tushare-flush", help="把本地缓冲重放到 NAS（tushare-backfill flush 失败后兜底）")
    p_tf.add_argument("--workers", type=int, default=1,
                       help="并发连接数，默认1(顺序，安全)。>1 时不保证跨行执行顺序，"
                            "只适合同表无依赖写入（如估值快照按日 upsert）")

    return p


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
        from data.etf_updater_cn import update_etf_prices
        n = update_etf_prices(full_rebase=True)
        print(f"[cn] ETF rebase wrote {n} rows to index_prices")
        return 0

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


def cmd_migrate_intraday() -> int:
    from modules.db_admin import create_prices_intraday_table
    create_prices_intraday_table()
    print("prices_intraday table ready")
    return 0


def cmd_intraday(interval: str | None, rebase: bool = False) -> int:
    from data.intraday_updater_us import update_intraday, SUPPORTED_INTERVALS
    intervals = [interval] if interval else SUPPORTED_INTERVALS
    for ivl in intervals:
        log.info(f"[intraday] 开始拉取 {ivl}" + (" (rebase)" if rebase else ""))
        result = update_intraday(ivl, full_rebase=rebase)
        ok = sum(1 for v in result.values() if v == "ok")
        err = sum(1 for v in result.values() if v.startswith("error"))
        log.info(f"[intraday {ivl}] 完成: ok={ok}, error={err}")
    return 0


def cmd_tushare_backfill(scope: str, market: str, dry_run: bool, start: str | None = None) -> int:
    """两阶段：backfill 写本地缓冲 → 自动 flush 到 NAS。flush 失败则保留缓冲、提示兜底。"""
    from core.db_client import set_local_first
    from ts_ingest.orchestrator import run_full_backfill
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
              f"缓冲 {n} 条待传保留。NAS 恢复后跑: uv run main.py tushare-flush")
        return 1
    return 0


def cmd_tushare_full(scope: str, market: str, dry_run: bool) -> int:
    """全量强制回填：起点固定为 TUSHARE_BACKFILL_START，等价 tushare-backfill --start 2010起。"""
    from config import TUSHARE_BACKFILL_START
    return cmd_tushare_backfill(scope, market, dry_run, start=TUSHARE_BACKFILL_START)


def cmd_tushare_sync(scope: str, market: str, dry_run: bool) -> int:
    """增量拉取：不传 start，各 domain 走自己的默认行为（能增量的增量，financial/dividend 接口限制仍全量）。"""
    return cmd_tushare_backfill(scope, market, dry_run, start=None)
    return 0


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
    from futu_ingest.orchestrator import run_sync
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
              f"缓冲 {n} 条待传保留。NAS 恢复后跑: uv run main.py futu-flush")
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
    if args.cmd == "weekly":
        return cmd_weekly(args.market, args.code)
    if args.cmd == "rebase":
        return cmd_rebase(args.market, args.code, args.years, args.index, args.etf_only)
    if args.cmd == "tushare-backfill":
        return cmd_tushare_backfill(args.scope, args.market, args.dry_run, args.start)
    if args.cmd == "tushare-full":
        return cmd_tushare_full(args.scope, args.market, args.dry_run)
    if args.cmd == "tushare-sync":
        return cmd_tushare_sync(args.scope, args.market, args.dry_run)
    if args.cmd == "tushare-flush":
        return cmd_tushare_flush(args.workers)
    if args.cmd == "futu-full":
        return cmd_futu_full(args.scope)
    if args.cmd == "futu-sync":
        return cmd_futu_sync(args.scope)
    if args.cmd == "futu-flush":
        return cmd_futu_flush()
    if args.cmd == "migrate-intraday":
        return cmd_migrate_intraday()
    if args.cmd == "intraday":
        return cmd_intraday(args.interval, args.rebase)
    return 1


if __name__ == "__main__":
    sys.exit(main())
