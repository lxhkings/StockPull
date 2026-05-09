"""Two-source price reconciliation.

Compares close prices from a primary and secondary source for the same
(ticker, date) pairs.  Mismatches beyond a configurable tolerance are
returned as a DataFrame for logging / alerting.

Usage:
    mismatches = reconcile_prices(primary_df, secondary_df, tolerance=0.005)
    if not mismatches.empty:
        log.warning(...)
"""

from __future__ import annotations

import logging

import pandas as pd

log = logging.getLogger(__name__)


def reconcile_prices(
    primary: pd.DataFrame,
    secondary: pd.DataFrame,
    tolerance: float = 0.005,
) -> pd.DataFrame:
    """Compare close prices between two sources.

    Both DataFrames must have columns: ``ticker``, ``date``, ``close``.

    Args:
        primary:   prices from the authoritative source (e.g. akshare hfq).
        secondary: prices from the cross-check source (e.g. efinance).
        tolerance: maximum relative difference considered a match (default 0.5 %).

    Returns:
        DataFrame of mismatched rows with an extra ``diff_pct`` column,
        ordered by descending absolute difference.  Empty DataFrame when
        all prices agree within tolerance.
    """
    required = {"ticker", "date", "close"}
    for name, df in [("primary", primary), ("secondary", secondary)]:
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"{name} DataFrame missing columns: {missing}")

    merged = primary.merge(
        secondary,
        on=["ticker", "date"],
        suffixes=("_primary", "_secondary"),
        how="inner",
    )

    if merged.empty:
        return pd.DataFrame(columns=["ticker", "date", "close_primary",
                                     "close_secondary", "diff_pct"])

    merged["diff_pct"] = (
        (merged["close_primary"] - merged["close_secondary"]).abs()
        / merged["close_primary"].abs().clip(lower=1e-9)
    )

    mismatches = merged[merged["diff_pct"] > tolerance].copy()
    mismatches = mismatches.sort_values("diff_pct", ascending=False).reset_index(drop=True)

    if not mismatches.empty:
        log.warning(f"Reconcile: {len(mismatches)} mismatches (tolerance={tolerance})")

    return mismatches
