"""yfinance DataFrame → 标准 OHLCV 列。纯转换，零 I/O。"""
from __future__ import annotations

import pandas as pd


def normalize_daily_frame(ticker: str, sub: pd.DataFrame) -> pd.DataFrame:
    """单 ticker 子表 → [ticker, date, open, high, low, close, volume]。"""
    cols = ["ticker", "date", "open", "high", "low", "close", "volume"]
    if sub is None or sub.empty:
        return pd.DataFrame(columns=cols)

    df = sub.reset_index()
    # 处理 MultiIndex 列名（yfinance 单 ticker 也返回 MultiIndex）
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df.columns = [str(c).lower() for c in df.columns]
    if "date" not in df.columns:
        for cand in ("datetime", "index"):
            if cand in df.columns:
                df = df.rename(columns={cand: "date"})
                break

    df["date"] = pd.to_datetime(df["date"]).dt.date
    df["ticker"] = ticker
    df = df.dropna(subset=["date", "close"])
    df = df[cols].sort_values("date").reset_index(drop=True)
    return df
