"""Shared Futu upsert + pagination helpers (not a framework)."""
from __future__ import annotations

import logging
from typing import Any

from core.db_client import get_conn

log = logging.getLogger(__name__)


def upsert_rows(
    table: str,
    columns: list[str],
    rows: list[tuple],
    update_columns: list[str],
    *,
    ticker: str | None = None,
) -> int:
    if not rows:
        return 0
    col_sql = ", ".join(columns)
    placeholders = ", ".join(["%s"] * len(columns))
    odku = ", ".join(f"{c}=VALUES({c})" for c in update_columns)
    sql = (
        f"INSERT INTO {table} ({col_sql}) VALUES ({placeholders}) "
        f"ON DUPLICATE KEY UPDATE {odku}"
    )
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.executemany(sql, rows)
        conn.commit()
    label = f"{table} {ticker}" if ticker else table
    log.info(f"{label}: {len(rows)} rows")
    return len(rows)


def paginate_call(
    client,
    method: str,
    code: str,
    *,
    list_key: str,
    page_num: int = 50,
    **kwargs: Any,
) -> list:
    """Paginate Futu APIs that use ``next_key`` / ``num`` style pagination.

    Only for next_key / num style APIs. Do **not** use for size-based pagers
    (e.g. snapshot batch loops that stop when ``len < PAGE_NUM``).

    Response shapes:
    - ``dict``: read ``list_key`` items and follow ``next_key`` until empty or ``"-1"``.
    - ``list``: treat as a single-page payload (the list itself is the page contents);
      return it with no further pages.
    - other: raise ``TypeError`` (avoids silent empty results from coerced ``{}``).
    """
    out: list = []
    next_key = None
    while True:
        data = client.call(method, code, next_key=next_key, num=page_num, **kwargs)
        if isinstance(data, list):
            # Single-page list response; no further pagination.
            out.extend(data)
            break
        if not isinstance(data, dict):
            raise TypeError(
                f"paginate_call expected dict or list from {method}, "
                f"got {type(data).__name__}"
            )
        chunk = data.get(list_key, []) or []
        out.extend(chunk)
        next_key = data.get("next_key", "-1")
        if not chunk or next_key == "-1":
            break
    return out
