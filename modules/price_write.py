"""
price_write.py — prices + sync_log 批写入（跨家族业务模块）

统一「写行情行 + 写 sync_log + 单次 commit」语义。
- on_duplicate=True  → INSERT ... ON DUPLICATE KEY UPDATE（CN/HK）
- on_duplicate=False → INSERT IGNORE（US）
"""

from __future__ import annotations

_ALLOWED_PRICE_TABLES = frozenset({"prices", "prices_weekly"})


def flush_prices_and_sync(
    conn,
    price_rows: list[tuple],
    sync_rows: list[tuple],
    *,
    on_duplicate: bool = True,
    price_table: str = "prices",
) -> None:
    """Write prices then sync_log rows, single commit.

    price_rows: (ticker, date, open, high, low, close, volume)
    sync_rows: (ticker, data_type, last_date, rows_added, status, message)
    on_duplicate=True → ON DUPLICATE KEY UPDATE (CN)
    on_duplicate=False → INSERT IGNORE (US)
    price_table: "prices" (default) or "prices_weekly" (CN weekly)
    """
    if not price_rows and not sync_rows:
        return

    if price_table not in _ALLOWED_PRICE_TABLES:
        raise ValueError(f"unsupported price_table: {price_table!r}")

    if price_rows:
        if on_duplicate:
            sql = f"""
                INSERT INTO {price_table} (ticker, date, open, high, low, close, volume)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    open=VALUES(open), high=VALUES(high), low=VALUES(low),
                    close=VALUES(close), volume=VALUES(volume)
            """
        else:
            sql = f"""
                INSERT IGNORE INTO {price_table} (ticker, date, open, high, low, close, volume)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """
        with conn.cursor() as cur:
            cur.executemany(sql, price_rows)

    if sync_rows:
        sync_sql = """
            INSERT INTO sync_log
              (ticker, data_type, last_date, rows_added, status, message)
            VALUES (%s,%s,%s,%s,%s,%s)
            ON DUPLICATE KEY UPDATE
              last_date  = IF(VALUES(status)='ok', VALUES(last_date), last_date),
              rows_added = VALUES(rows_added),
              last_run   = CURRENT_TIMESTAMP,
              status     = VALUES(status),
              message    = VALUES(message)
        """
        with conn.cursor() as cur:
            cur.executemany(sync_sql, sync_rows)

    conn.commit()
