"""Rate limiting for the endpoints that cost money.

Every investigation, question, targeted challenge and evaluation run triggers
billable inference. Without a limit, one caller can drive unbounded spend, which
turns cost into an attack surface rather than a budget line. That is the gap this
closes.

Read endpoints are deliberately *not* limited. They serve stored rows, cost
nothing, and throttling them would only degrade the interface for the analyst
whose dashboard is polling it.

Implemented as a FastAPI dependency rather than a decorator, because decorators
that wrap the handler break FastAPI's signature introspection - it stops seeing
the real parameters and starts treating the request body as query arguments. A
dependency composes cleanly and leaves handler signatures untouched.

**What this is not.** The counter is an in-process sliding window keyed on client
address. That is right for a single-instance prototype and wrong for anything
else: it does not survive a restart, it does not coordinate across replicas, and
a client behind a shared NAT shares a bucket. Production needs a shared store
(Redis) and a key based on the authenticated principal rather than the address,
with a per-tenant budget alongside it. See docs/architecture/security.md.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from threading import Lock

from fastapi import HTTPException, Request, status

from argus_api.core.settings import get_settings

WINDOW_SECONDS = 60.0

# Per-key timestamps of recent accepted calls. Bounded by eviction on read.
_hits: dict[str, deque[float]] = defaultdict(deque)
_lock = Lock()


def _client_key(request: Request) -> str:
    """Identify the caller.

    Honours ``X-Forwarded-For`` only for its first entry, since that is the
    original client when a single trusted proxy sits in front. Behind an
    untrusted proxy this header is spoofable, which is one more reason the
    production key should be an authenticated principal.
    """
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _record(key: str, limit: int) -> tuple[bool, int]:
    """Register a call. Returns whether it is allowed and seconds until reset."""
    now = time.monotonic()
    cutoff = now - WINDOW_SECONDS

    with _lock:
        bucket = _hits[key]
        while bucket and bucket[0] < cutoff:
            bucket.popleft()

        if len(bucket) >= limit:
            retry_after = int(WINDOW_SECONDS - (now - bucket[0])) + 1
            return False, retry_after

        bucket.append(now)
        return True, 0


def enforce_inference_limit(request: Request) -> None:
    """Dependency for routes that trigger inference.

    Use as ``dependencies=[Depends(enforce_inference_limit)]`` on the route.

    Raises:
        HTTPException: 429 when the caller has exceeded the configured rate.
    """
    limit = get_settings().rate_limit_per_minute
    if limit <= 0:
        return  # A non-positive limit disables throttling entirely.

    allowed, retry_after = _record(_client_key(request), limit)
    if allowed:
        return

    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=(
            f"Rate limit reached ({limit} model-backed requests per minute). "
            "These endpoints trigger inference, so they are limited to keep "
            "cost bounded. Retry shortly."
        ),
        headers={"Retry-After": str(retry_after)},
    )


def reset() -> None:
    """Clear all counters. Used by tests."""
    with _lock:
        _hits.clear()
