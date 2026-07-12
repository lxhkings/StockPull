"""Legacy CLI argv rewrite + deprecation warning."""

from __future__ import annotations

import sys

# 旧顶层命令 → 新二级命令前缀（其余 argv 原样拼在后面）
_LEGACY_PREFIX: dict[str, list[str]] = {
    "daily": ["prices", "daily"],
    "weekly": ["prices", "weekly"],
    "intraday": ["prices", "intraday"],
    "rebase": ["prices", "rebase"],
    "tushare-sync": ["tushare", "sync"],
    "tushare-full": ["tushare", "full"],
    "tushare-backfill": ["tushare", "sync"],
    "tushare-flush": ["tushare", "flush"],
    "futu-sync": ["futu", "sync"],
    "futu-full": ["futu", "full"],
    "futu-flush": ["futu", "flush"],
    "migrate-intraday": ["db", "migrate-intraday"],
}


def warn_deprecated(old: str, new: str) -> None:
    print(
        f"[deprecated] `{old}` → 请改用 `{new}`（旧命令仍可用，将在后续版本移除）",
        file=sys.stderr,
    )


def rewrite_legacy_argv(argv: list[str] | None) -> list[str] | None:
    """把旧顶层命令改写成新二级命令；非 legacy 原样返回。

    例: ['daily', '--market', 'us'] → ['prices', 'daily', '--market', 'us']
    """
    if not argv:
        return argv
    head = argv[0]
    prefix = _LEGACY_PREFIX.get(head)
    if prefix is None:
        return argv
    warn_deprecated(head, " ".join(prefix))
    return prefix + argv[1:]
