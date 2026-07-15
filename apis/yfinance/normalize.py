"""yfinance DataFrame → 标准 OHLCV 列。纯转换，零 I/O。"""
from __future__ import annotations

import pandas as pd


def lower_ohlc_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Flatten MultiIndex / tuple column names to level-0 and lower-case them.

    Shared by daily/intraday normalize and prices_index (close-only). Mutates columns.
    """
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df.columns = [
        str(c).lower() if not isinstance(c, tuple) else str(c[0]).lower()
        for c in df.columns
    ]
    return df


def normalize_daily_frame(ticker: str, sub: pd.DataFrame) -> pd.DataFrame:
    """单 ticker 子表 → [ticker, date, open, high, low, close, volume]。"""
    cols = ["ticker", "date", "open", "high", "low", "close", "volume"]
    if sub is None or sub.empty:
        return pd.DataFrame(columns=cols)

    df = lower_ohlc_columns(sub.reset_index())
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


def normalize_intraday_frame(ticker: str, interval: str, sub: pd.DataFrame) -> pd.DataFrame:
    """yfinance 单 ticker 子表 → 标准列 [ticker, interval, datetime, open, high, low, close, volume]"""
    cols = ["ticker", "interval", "datetime", "open", "high", "low", "close", "volume"]
    if sub is None or sub.empty:
        return pd.DataFrame(columns=cols)

    df = lower_ohlc_columns(sub.reset_index())

    for cand in ("datetime", "date", "index"):
        if cand in df.columns:
            df = df.rename(columns={cand: "datetime"})
            break

    df["datetime"] = pd.to_datetime(df["datetime"])
    # 剥除时区，MySQL DATETIME 无时区（yfinance 返回 UTC）
    if df["datetime"].dt.tz is not None:
        df["datetime"] = df["datetime"].dt.tz_convert("UTC").dt.tz_localize(None)

    df["ticker"] = ticker
    df["interval"] = interval
    df = df.dropna(subset=["datetime", "close"])
    return df[cols].sort_values("datetime").reset_index(drop=True)
