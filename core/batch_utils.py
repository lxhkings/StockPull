"""batch_utils.py — 列表分批切片。

此前 stock_updater_us.py / stock_updater_us_weekly.py / intraday_updater_us.py /
core/local_buffer.py / futu_ingest/snapshot_daily.py 各自写了一份
range(0, len(x), N) 切片循环，本模块收敛为单一生成器。
"""
from __future__ import annotations

from typing import Iterator, Sequence, TypeVar

T = TypeVar("T")


def chunked(seq: Sequence[T], size: int) -> Iterator[Sequence[T]]:
    for i in range(0, len(seq), size):
        yield seq[i:i + size]
