"""Sliding-window rate limiter shared across API modules."""

from collections import defaultdict
import time as _time


class RateLimiter:
    """Sliding-window rate limiter. Not thread-safe, but GIL + single event loop makes it OK."""

    def __init__(self, max_requests: int = 10, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._store: dict[str, list[float]] = defaultdict(list)

    def is_allowed(self, key: str) -> bool:
        now = _time.time()
        timestamps = self._store[key]
        # Purge expired entries
        cutoffs = [t for t in timestamps if now - t < self.window_seconds]
        timestamps[:] = cutoffs
        if len(timestamps) >= self.max_requests:
            return False
        timestamps.append(now)
        return True
