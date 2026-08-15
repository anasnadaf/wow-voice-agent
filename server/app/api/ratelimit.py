"""Tiny in-memory per-IP rate limiter for the public call-request endpoint.

Good enough for a single-process deployment; swap for Redis if we ever scale out.
"""

import time
from collections import defaultdict

from fastapi import HTTPException, Request


class RateLimiter:
    def __init__(self, limit: int = 5, window_s: int = 3600) -> None:
        self.limit = limit
        self.window_s = window_s
        self._hits: dict[str, list[float]] = defaultdict(list)

    def check(self, key: str) -> None:
        now = time.monotonic()
        hits = self._hits[key] = [t for t in self._hits[key] if now - t < self.window_s]
        if len(hits) >= self.limit:
            raise HTTPException(
                status_code=429, detail="Too many call requests; please try again later"
            )
        hits.append(now)

    def reset(self) -> None:
        self._hits.clear()


public_call_limiter = RateLimiter(limit=5, window_s=3600)


def client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
