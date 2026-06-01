"""RateLimiter 线程安全：并发 wait 不破限频窗口。"""
import threading
import time

from data.base import RateLimiter


def test_rate_limiter_threadsafe_spacing():
    """N 线程并发调 wait()，相邻放行间隔不得小于 delay（容忍调度抖动）。"""
    delay = 0.05
    limiter = RateLimiter(delay)
    stamps: list[float] = []
    lock = threading.Lock()

    def worker():
        limiter.wait()
        with lock:
            stamps.append(time.monotonic())

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    stamps.sort()
    gaps = [b - a for a, b in zip(stamps, stamps[1:])]
    # 锁覆盖 sleep → 每次放行间隔 ≥ delay（留 10% 容差应对计时抖动）
    assert all(g >= delay * 0.9 for g in gaps), gaps
    assert len(stamps) == 10
