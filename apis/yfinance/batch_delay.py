"""Shared inter-batch sleep for yfinance multi-ticker downloads."""
from __future__ import annotations

import logging
import random
import time

from config import YF_BATCH_DELAY_BASE, YF_BATCH_DELAY_JITTER

log = logging.getLogger(__name__)


def sleep_between_batches(label: str) -> None:
    """Sleep YF_BATCH_DELAY_BASE ± jitter between download batches."""
    delay = YF_BATCH_DELAY_BASE + random.uniform(
        -YF_BATCH_DELAY_JITTER, YF_BATCH_DELAY_JITTER
    )
    log.debug(f"[{label}] 等待 {delay:.1f}s 后继续")
    time.sleep(delay)
