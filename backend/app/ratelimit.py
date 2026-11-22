"""Small in-memory sliding-window rate limiter for the auth endpoints.

Per process: fine for a single Render instance. With several instances, move this to a shared
store (Redis or the database).
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status

_hits: dict[str, deque] = defaultdict(deque)
_lock = threading.Lock()


def reset() -> None:
    with _lock:
        _hits.clear()


def limit(name: str, max_calls: int, window_seconds: int):
    def dep(request: Request) -> None:
        ip = request.client.host if request.client else "unknown"
        key = f"{name}:{ip}"
        now = time.monotonic()
        with _lock:
            q = _hits[key]
            while q and now - q[0] > window_seconds:
                q.popleft()
            if len(q) >= max_calls:
                raise HTTPException(
                    status.HTTP_429_TOO_MANY_REQUESTS, "Too many attempts. Please wait a few minutes and try again."
                )
            q.append(now)

    return dep
