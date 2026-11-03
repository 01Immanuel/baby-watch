"""Small in-memory sliding-window rate limiter. Protects the free LLM quota and the API key."""
import time
from collections import deque


class RateLimiter:
    def __init__(self, limit, window=60.0, clock=time.monotonic, max_keys=10_000):
        self.limit, self.window, self.clock, self.max_keys = limit, window, clock, max_keys
        self.hits = {}

    def allow(self, key):
        """Return (allowed, retry_after_seconds)."""
        if self.limit <= 0:  # 0 disables limiting
            return True, 0.0
        now = self.clock()
        q = self.hits.setdefault(key, deque())
        while q and now - q[0] >= self.window:
            q.popleft()
        if len(q) >= self.limit:
            return False, max(self.window - (now - q[0]), 0.0)
        q.append(now)
        if len(self.hits) > self.max_keys:
            self._prune(now)
        return True, 0.0

    def _prune(self, now):
        for k in [k for k, q in self.hits.items() if not q or now - q[-1] >= self.window]:
            del self.hits[k]
