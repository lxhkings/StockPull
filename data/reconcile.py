"""Two-source reconciliation for A-share / HK daily-K data.

Strategy:
  - For each (ticker, date) row, compare close.
  - Within tolerance: take primary's row.
  - Beyond tolerance: log mismatch, still take primary's row.
  - Only one source has the row: pass through.
"""

from __future__ import annotations

import logging
from typing import List, Tuple

import pandas as pd

from config import RECONCILE_PRICE_TOLERANCE

log = logging.getLogger(__name__)


def reconcile_two_sources(
    primary: pd.DataFrame,
    secondary: pd.DataFrame,
    tolerance: float = RECONCILE_PRICE_TOLERANCE,
) -> Tuple[pd.DataFrame, List[dict]]:
    """Merge two daily-K DataFrames by (ticker, date), preferring primary.

    Returns:
      (merged_df, mismatches)  — mismatches: list of {ticker, date, primary, secondary}
    """
    cols = ["ticker", "date", "open", "high", "low", "close", "volume"]

    if primary.empty and secondary.empty:
        return pd.DataFrame(columns=cols), []

    if primary.empty:
        return secondary[cols].reset_index(drop=True), []

    if secondary.empty:
        return primary[cols].reset_index(drop=True), []

    p = primary.set_index(["ticker", "date"])
    s = secondary.set_index(["ticker", "date"])

    common = p.index.intersection(s.index)
    only_secondary = s.index.difference(p.index)

    mismatches: List[dict] = []
    for idx in common:
        p_close = float(p.loc[idx, "close"])
        s_close = float(s.loc[idx, "close"])
        if p_close == 0:
            continue
        if abs(p_close - s_close) / p_close > tolerance:
            ticker, dt = idx
            log.warning(
                f"[reconcile] {ticker} {dt}: primary close={p_close} vs secondary={s_close} "
                f"(diff {abs(p_close-s_close)/p_close*100:.2f}%)"
            )
            mismatches.append({
                "ticker": ticker, "date": dt,
                "primary": p_close, "secondary": s_close,
            })

    # Build merged: all primary + secondary-only
    merged = pd.concat([
        p,
        s.loc[only_secondary] if len(only_secondary) > 0 else pd.DataFrame(),
    ])
    merged = merged.reset_index().sort_values(["ticker", "date"]).reset_index(drop=True)
    return merged[cols], mismatches
