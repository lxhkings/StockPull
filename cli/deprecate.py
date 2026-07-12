from __future__ import annotations

import sys


def warn_deprecated(old: str, new: str) -> None:
    print(
        f"[deprecated] `{old}` → 请改用 `{new}`（旧命令仍可用，将在后续版本移除）",
        file=sys.stderr,
    )
