import threading
import time
from collections import defaultdict, deque


class RateLimiter:
    """In-process sliding-window rate limiter. Thread-safe; single-worker deployments only."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._windows: dict[str, deque[float]] = defaultdict(deque)

    def _prune(self, key: str, cutoff: float) -> None:
        dq = self._windows[key]
        while dq and dq[0] <= cutoff:
            dq.popleft()

    def hit(self, key: str, limit: int, window_seconds: int) -> int:
        """Record a hit. Returns 0 if within limit, else seconds until the oldest slot expires."""
        with self._lock:
            now = time.monotonic()
            self._prune(key, now - window_seconds)
            dq = self._windows[key]
            if len(dq) >= limit:
                return max(1, int(dq[0] + window_seconds - now) + 1)
            dq.append(now)
            return 0

    def is_blocked(self, key: str, limit: int, window_seconds: int) -> int:
        """Check without recording. Returns 0 if under limit, else retry-after seconds."""
        with self._lock:
            now = time.monotonic()
            self._prune(key, now - window_seconds)
            dq = self._windows[key]
            if len(dq) >= limit:
                return max(1, int(dq[0] + window_seconds - now) + 1)
            return 0
