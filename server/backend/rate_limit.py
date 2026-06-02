import logging
import threading
import time
from collections import deque

logger = logging.getLogger(__name__)


def client_ip(headers, client) -> str:
    """Return the real client IP from the X-Real-IP header set by the nginx proxy.

    Falls back to the socket address with a warning — in production this path should
    never be reached because nginx always sets X-Real-IP. A warning firing means the
    proxy is misconfigured and rate limiting is keying off the wrong address.
    """
    real_ip = headers.get("x-real-ip")
    if real_ip:
        return real_ip
    fallback = client.host if client else "unknown"
    logger.warning("X-Real-IP header missing — using socket address %r as rate-limit key", fallback)
    return fallback


class RateLimiter:
    """In-process sliding-window rate limiter. Thread-safe; single-worker deployments only."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._windows: dict[str, deque[float]] = {}

    def _prune(self, key: str, cutoff: float) -> deque[float] | None:
        """Remove expired timestamps and delete the entry if it becomes empty.
        Returns the deque if it still has entries, else None."""
        dq = self._windows.get(key)
        if dq is None:
            return None
        while dq and dq[0] <= cutoff:
            dq.popleft()
        if not dq:
            del self._windows[key]
            return None
        return dq

    def hit(self, key: str, limit: int, window_seconds: int) -> int:
        """Record a hit. Returns 0 if within limit, else seconds until the oldest slot expires."""
        with self._lock:
            now = time.monotonic()
            dq = self._prune(key, now - window_seconds)
            if dq is None:
                dq = self._windows[key] = deque()
            if len(dq) >= limit:
                return max(1, int(dq[0] + window_seconds - now) + 1)
            dq.append(now)
            return 0

    def is_blocked(self, key: str, limit: int, window_seconds: int) -> int:
        """Check without recording. Returns 0 if under limit, else retry-after seconds."""
        with self._lock:
            now = time.monotonic()
            dq = self._prune(key, now - window_seconds)
            if dq is None:
                return 0
            if len(dq) >= limit:
                return max(1, int(dq[0] + window_seconds - now) + 1)
            return 0
