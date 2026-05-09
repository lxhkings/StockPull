# tests/test_reconcile.py
import pandas as pd
from datetime import date


def _df(closes, dates=None):
    dates = dates or [date(2024, 1, d) for d in range(2, 2 + len(closes))]
    return pd.DataFrame({
        "ticker": ["600519.SH"] * len(closes),
        "date":   dates,
        "open":   [c - 1 for c in closes],
        "high":   [c + 5 for c in closes],
        "low":    [c - 5 for c in closes],
        "close":  closes,
        "volume": [1000] * len(closes),
    })


def test_both_sources_agree_uses_primary():
    from data.reconcile import reconcile_two_sources
    a = _df([1700.0, 1710.0])
    b = _df([1700.5, 1710.3])  # within 0.5%
    merged, mismatches = reconcile_two_sources(a, b, tolerance=0.005)
    assert len(merged) == 2
    assert merged["close"].tolist() == [1700.0, 1710.0]   # primary wins
    assert mismatches == []


def test_disagreement_logged_but_primary_wins():
    from data.reconcile import reconcile_two_sources
    a = _df([1700.0, 1710.0])
    b = _df([1700.0, 1900.0])   # day 2 diverges 11%
    merged, mismatches = reconcile_two_sources(a, b, tolerance=0.005)
    assert merged["close"].tolist() == [1700.0, 1710.0]
    assert len(mismatches) == 1
    assert mismatches[0]["date"] == date(2024, 1, 3)
    assert mismatches[0]["primary"] == 1710.0
    assert mismatches[0]["secondary"] == 1900.0


def test_only_primary_passes_through():
    from data.reconcile import reconcile_two_sources
    a = _df([1700.0])
    b = pd.DataFrame(columns=a.columns)
    merged, mismatches = reconcile_two_sources(a, b)
    assert len(merged) == 1
    assert mismatches == []


def test_only_secondary_used_when_primary_empty():
    from data.reconcile import reconcile_two_sources
    a = pd.DataFrame(columns=["ticker", "date", "open", "high", "low", "close", "volume"])
    b = _df([1700.0])
    merged, mismatches = reconcile_two_sources(a, b)
    assert len(merged) == 1
    assert merged["close"].iloc[0] == 1700.0
