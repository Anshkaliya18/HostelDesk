"""Small in-memory sliding-window rate limiter (no external dependency).

Per-process only: counters restart on deployment and are not shared across
workers. Good enough for the hackathon (and honest about it in the docs).

Keys are caller-supplied strings (e.g. ``complaint:{user_id}``,
``signup:{client_ip}``). ``check`` prunes expired events, then either records
the event and returns True, or rejects and returns False.
"""

import threading
import time
from collections import deque


class SlidingWindowLimiter:
    def __init__(self) -> None:
        self._events: dict[str, deque[float]] = {}
        self._lock = threading.Lock()
        self._clock = time.monotonic  # swappable for tests

    def check(self, key: str, limit: int, window_seconds: float) -> bool:
        """Record one event unless the key already hit ``limit`` in the window."""
        with self._lock:
            now = self._clock()
            events = self._events.setdefault(key, deque())
            cutoff = now - window_seconds
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= limit:
                return False
            events.append(now)
            # Opportunistically drop keys that are now empty after pruning.
            if not events:
                self._events.pop(key, None)
            return True

    def clear(self) -> None:
        with self._lock:
            self._events.clear()


complaint_limiter = SlidingWindowLimiter()
signup_limiter = SlidingWindowLimiter()


def clear_all() -> None:
    """Test helper: reset every limiter above (call between tests)."""
    complaint_limiter.clear()
    signup_limiter.clear()


def client_ip(request) -> str:
    """First hop of X-Forwarded-For when present (behind Render/Cloudflare),
    otherwise the direct connection address."""
    forwarded = request.headers.get("x-forwarded-for") or ""
    first_hop = forwarded.split(",", 1)[0].strip()
    return first_hop or (request.client.host if request.client else "unknown")
