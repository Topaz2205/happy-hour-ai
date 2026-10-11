import os
from collections import defaultdict, deque
from threading import Lock
from time import monotonic

from fastapi import HTTPException, Request


WINDOW_SECONDS = int(os.getenv("AI_DEMO_WINDOW_SECONDS", "600"))
PER_USER_LIMIT = int(os.getenv("AI_DEMO_USER_LIMIT", "8"))
GLOBAL_LIMIT = int(os.getenv("AI_DEMO_GLOBAL_LIMIT", "40"))

ENABLED = os.getenv("AI_DEMO_RATE_LIMIT_ENABLED", "0").lower() in {
    "1", "true", "yes", "on"
}

_user_requests: dict[str, deque[float]] = defaultdict(deque)
_global_requests: deque[float] = deque()
_lock = Lock()


def _client_key(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()

    if request.client:
        return request.client.host

    return "unknown"


def _purge(queue: deque[float], now: float) -> None:
    cutoff = now - WINDOW_SECONDS
    while queue and queue[0] <= cutoff:
        queue.popleft()


def enforce_ai_rate_limit(request: Request) -> None:
    if not ENABLED:
        return

    now = monotonic()
    client = _client_key(request)

    with _lock:
        _purge(_global_requests, now)

        user_queue = _user_requests[client]
        _purge(user_queue, now)

        if len(_global_requests) >= GLOBAL_LIMIT:
            raise HTTPException(
                status_code=429,
                detail=(
                    "The public AI demo is temporarily busy. "
                    "Please wait a few minutes and try again."
                ),
                headers={"Retry-After": "60"},
            )

        if len(user_queue) >= PER_USER_LIMIT:
            raise HTTPException(
                status_code=429,
                detail=(
                    "You've reached the AI limit for the public demo. "
                    "Please wait a few minutes and try again."
                ),
                headers={"Retry-After": "60"},
            )

        user_queue.append(now)
        _global_requests.append(now)
