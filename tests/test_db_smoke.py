"""Live DB smoke test. Skip with `pytest -m 'not smoke'` if NAS unreachable."""

import pytest
import socket
from datetime import date


def _nas_reachable():
    try:
        with socket.create_connection(("192.168.8.9", 3306), timeout=2):
            return True
    except OSError:
        return False


pytestmark = pytest.mark.skipif(not _nas_reachable(), reason="NAS DB not reachable")


def test_get_conn_succeeds():
    from db import get_conn
    conn = get_conn()
    try:
        assert conn.open
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            assert cur.fetchone() == (1,)
    finally:
        conn.close()


def test_existing_schema_tables_present():
    """Confirm we are talking to the right DB (the one stock_system uses)."""
    from db import query
    rows = query("SHOW TABLES")
    table_names = {next(iter(r.values())) for r in rows}
    expected = {"stocks", "prices", "indices", "index_constituents",
                "constituent_changes", "index_prices", "sync_log", "index_sync_log"}
    assert expected.issubset(table_names), f"Missing tables: {expected - table_names}"


def test_sync_log_roundtrip():
    """Write/read a probe row in sync_log."""
    from db import get_conn, set_sync_ok, get_last_sync
    conn = get_conn()
    try:
        probe_ticker = "__PROBE__"
        set_sync_ok(conn, probe_ticker, "price", date(2026, 5, 9), 0)
        last = get_last_sync(conn, probe_ticker, "price")
        assert last == date(2026, 5, 9)
        # Cleanup
        with conn.cursor() as cur:
            cur.execute("DELETE FROM sync_log WHERE ticker=%s", (probe_ticker,))
        conn.commit()
    finally:
        conn.close()
