"""周/月线转换：日线 resample + row tuple 构造。纯函数，零 I/O。"""
from __future__ import annotations

import pandas as pd


def resample_ohlcv(daily: pd.DataFrame, freq: str) -> pd.DataFrame:
    if daily.empty:
        return pd.DataFrame()
    df = daily.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date")
    out = df.resample(freq).agg({
        "open":   "first",
        "high":   "max",
        "low":    "min",
        "close":  "last",
        "volume": "sum",
    }).dropna(subset=["close"])
    out = out.reset_index()
    out["date"] = out["date"].dt.date
    return out


def periodic_rows(ticker: str, df: pd.DataFrame) -> list[tuple]:
    if df.empty:
        return []
    return [
        (ticker, r["date"], float(r["open"]), float(r["high"]),
         float(r["low"]), float(r["close"]), int(r["volume"]))
        for _, r in df.iterrows()
    ]
