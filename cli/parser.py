"""CLI argument parser: new secondary commands + suppressed legacy top-level."""

from __future__ import annotations

import argparse

MARKETS = ("us", "cn", "hk", "all")
_TS_SCOPES = (
    "all", "lists", "prices", "derive", "financial", "valuation", "shareholder_return",
)
_FUTU_SCOPES = (
    "all", "other", "daily", "weekly", "financial", "earnings", "actions",
    "profile", "revenue", "shareholders", "efficiency",
)


def _hide_suppressed(sub: argparse._SubParsersAction) -> None:
    """argparse 对 help=SUPPRESS 的子命令仍会列出 `==SUPPRESS==`；从 help 列表移除。"""
    sub._choices_actions = [
        a for a in sub._choices_actions if a.help is not argparse.SUPPRESS
    ]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="main.py", description="StockPull ingest CLI")
    # metavar 只展示新顶层，避免 usage 行堆满旧名（旧命令仍可解析）
    sub = p.add_subparsers(
        dest="cmd",
        required=True,
        metavar="{prices,tushare,futu,init,status,db}",
    )

    # --- prices ---
    p_prices = sub.add_parser("prices", help="行情：日线/周线/分钟线/rebase")
    ps = p_prices.add_subparsers(dest="prices_cmd", required=True)

    p_daily = ps.add_parser("daily", help="Run incremental daily ingest")
    p_daily.add_argument("--market", choices=MARKETS, default="all")
    p_daily.add_argument("--code", action="append", default=None,
                         help="Only this ticker (repeatable, debug aid)")
    p_daily.add_argument("--index", default=None,
                         help="指数成分股（仅 US 市场：SP500）")

    p_weekly = ps.add_parser("weekly", help="Run weekly ingest (US/CN market)")
    p_weekly.add_argument("--market", choices=("us", "cn"), default="us")
    p_weekly.add_argument("--code", action="append", default=None,
                          help="Only this ticker (repeatable, debug aid)")

    p_intraday = ps.add_parser("intraday", help="拉取美股分钟级行情（15m / 1h）并写入 prices_intraday")
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

    p_rebase = ps.add_parser("rebase", help="Full re-pull (qfq drift fix)")
    p_rebase.add_argument("--market", choices=("cn", "hk", "us"), required=True)
    p_rebase.add_argument("--code", action="append", default=None)
    p_rebase.add_argument("--years", type=int, default=None, help="历史年数（默认：US=5, CN/HK=15）")
    p_rebase.add_argument("--index", default=None,
                          help="指数成分股（仅 US 市场：SP500）")
    p_rebase.add_argument("--etf-only", action="store_true",
                          help="仅重灌 ETF index_prices（仅 CN 市场）")

    # --- tushare ---
    p_ts_root = sub.add_parser("tushare", help="Tushare 回填与 flush")
    ts = p_ts_root.add_subparsers(dest="tushare_cmd", required=True)

    p_ts_sync = ts.add_parser(
        "sync",
        help="Tushare 增量/自定义起点（无 --start 增量；有 --start 强制起点）",
    )
    p_ts_sync.add_argument("--scope", choices=_TS_SCOPES, default="all")
    p_ts_sync.add_argument("--market", choices=("all", "cn", "hk", "us"), default="all")
    p_ts_sync.add_argument("--dry-run", action="store_true")
    p_ts_sync.add_argument(
        "--start", default=None,
        help="YYYYMMDD，强制指定起点重新回填历史（valuation 默认从上次同步点增量续拉，"
             "需要这个才会往回填；financial 默认已是 TUSHARE_BACKFILL_START 全量，"
             "传了就换成这个起点）",
    )

    p_ts_full = ts.add_parser(
        "full",
        help="Tushare 全量强制回填（=tushare sync --start 2010起；"
             "financial/dividend 接口本来就每次全量，无实际差异）",
    )
    p_ts_full.add_argument("--scope", choices=_TS_SCOPES, default="all")
    p_ts_full.add_argument("--market", choices=("all", "cn", "hk", "us"), default="all")
    p_ts_full.add_argument("--dry-run", action="store_true")

    p_ts_flush = ts.add_parser(
        "flush",
        help="把本地缓冲重放到 NAS（tushare sync/full flush 失败后兜底）",
    )
    p_ts_flush.add_argument(
        "--workers", type=int, default=1,
        help="并发连接数，默认1(顺序，安全)。>1 时不保证跨行执行顺序，"
             "只适合同表无依赖写入（如估值快照按日 upsert）",
    )

    # --- futu ---
    p_fu = sub.add_parser("futu", help="Futu 采集与 flush")
    fs = p_fu.add_subparsers(dest="futu_cmd", required=True)

    p_fu_sync = fs.add_parser("sync", help="Futu 增量采集（按接口频率节流，cron 每日跑）")
    p_fu_sync.add_argument("--scope", choices=_FUTU_SCOPES, default="all")
    p_fu_full = fs.add_parser("full", help="Futu 全量采集（忽略节流，强制重拉）")
    p_fu_full.add_argument("--scope", choices=_FUTU_SCOPES, default="all")
    fs.add_parser("flush", help="把本地缓冲重放到 NAS（futu full/sync flush 失败后兜底）")

    # --- init / status ---
    sub.add_parser("init", help="Insert SP500/HSI rows into indices table (idempotent)")
    sub.add_parser("status", help="Print ingest status summary")

    # --- db ---
    p_db = sub.add_parser("db", help="数据库维护")
    dbs = p_db.add_subparsers(dest="db_cmd", required=True)
    dbs.add_parser("migrate-intraday", help="Create prices_intraday table (idempotent)")
    p_purge = dbs.add_parser(
        "purge-index",
        help="按 index_id 清理指数相关表（默认 dry-run，加 --yes 才删除）",
    )
    p_purge.add_argument(
        "--index-id", required=True,
        help="要清理的 index_id（如 CSI800、废弃的自定义 id）",
    )
    p_purge.add_argument(
        "--yes", action="store_true",
        help="确认删除；不加则只打印各表行数（dry-run）",
    )

    # --- legacy top-level (hidden from -h, still callable) ---
    p_daily_old = sub.add_parser("daily", help=argparse.SUPPRESS)
    p_daily_old.add_argument("--market", choices=MARKETS, default="all")
    p_daily_old.add_argument("--code", action="append", default=None,
                             help="Only this ticker (repeatable, debug aid)")
    p_daily_old.add_argument("--index", default=None,
                             help="指数成分股（仅 US 市场：SP500）")

    p_rebase_old = sub.add_parser("rebase", help=argparse.SUPPRESS)
    p_rebase_old.add_argument("--market", choices=("cn", "hk", "us"), required=True)
    p_rebase_old.add_argument("--code", action="append", default=None)
    p_rebase_old.add_argument("--years", type=int, default=None, help="历史年数（默认：US=5, CN/HK=15）")
    p_rebase_old.add_argument("--index", default=None,
                              help="指数成分股（仅 US 市场：SP500）")
    p_rebase_old.add_argument("--etf-only", action="store_true",
                              help="仅重灌 ETF index_prices（仅 CN 市场）")

    p_weekly_old = sub.add_parser("weekly", help=argparse.SUPPRESS)
    p_weekly_old.add_argument("--market", choices=("us", "cn"), default="us")
    p_weekly_old.add_argument("--code", action="append", default=None,
                              help="Only this ticker (repeatable, debug aid)")

    sub.add_parser("migrate-intraday", help=argparse.SUPPRESS)

    p_intraday_old = sub.add_parser("intraday", help=argparse.SUPPRESS)
    p_intraday_old.add_argument(
        "--interval",
        choices=["15m", "1h"],
        default=None,
        help="仅拉取指定 interval（默认：15m 和 1h 均拉）",
    )
    p_intraday_old.add_argument(
        "--rebase",
        action="store_true",
        default=False,
        help="全量回补，忽略 sync_log，拉满最大可得历史（1h=730天，15m=60天）",
    )

    p_ts_old = sub.add_parser("tushare-backfill", help=argparse.SUPPRESS)
    p_ts_old.add_argument("--scope", choices=_TS_SCOPES, default="all")
    p_ts_old.add_argument("--market", choices=("all", "cn", "hk", "us"), default="all")
    p_ts_old.add_argument("--dry-run", action="store_true")
    p_ts_old.add_argument(
        "--start", default=None,
        help="YYYYMMDD，强制指定起点重新回填历史（valuation 默认从上次同步点增量续拉，"
             "需要这个才会往回填；financial 默认已是 TUSHARE_BACKFILL_START 全量，"
             "传了就换成这个起点）",
    )

    p_tfull_old = sub.add_parser("tushare-full", help=argparse.SUPPRESS)
    p_tfull_old.add_argument("--scope", choices=_TS_SCOPES, default="all")
    p_tfull_old.add_argument("--market", choices=("all", "cn", "hk", "us"), default="all")
    p_tfull_old.add_argument("--dry-run", action="store_true")

    p_tsync_old = sub.add_parser("tushare-sync", help=argparse.SUPPRESS)
    p_tsync_old.add_argument("--scope", choices=_TS_SCOPES, default="all")
    p_tsync_old.add_argument("--market", choices=("all", "cn", "hk", "us"), default="all")
    p_tsync_old.add_argument("--dry-run", action="store_true")

    p_ff_old = sub.add_parser("futu-full", help=argparse.SUPPRESS)
    p_ff_old.add_argument("--scope", choices=_FUTU_SCOPES, default="all")
    p_fs_old = sub.add_parser("futu-sync", help=argparse.SUPPRESS)
    p_fs_old.add_argument("--scope", choices=_FUTU_SCOPES, default="all")
    sub.add_parser("futu-flush", help=argparse.SUPPRESS)

    p_tf_old = sub.add_parser("tushare-flush", help=argparse.SUPPRESS)
    p_tf_old.add_argument(
        "--workers", type=int, default=1,
        help="并发连接数，默认1(顺序，安全)。>1 时不保证跨行执行顺序，"
             "只适合同表无依赖写入（如估值快照按日 upsert）",
    )

    _hide_suppressed(sub)
    return p
