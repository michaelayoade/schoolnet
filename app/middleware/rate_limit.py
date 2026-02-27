"""Redis-backed sliding window rate limiter for auth endpoints.

Protects login, password reset, and MFA verification from brute-force attacks.
"""
from __future__ import annotations

import logging
import os
import time
from collections import deque
from threading import Lock

from cachetools import TTLCache
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

logger = logging.getLogger(__name__)

# Paths and their rate limit configs: (max_requests, window_seconds)
_RATE_LIMIT_PATHS: dict[str, tuple[int, int]] = {
    "/auth/login": (10, 60),           # 10 attempts per minute
    "/auth/password-reset": (5, 300),  # 5 attempts per 5 minutes
    "/auth/mfa/verify": (10, 60),      # 10 attempts per minute
    "/auth/register": (5, 300),        # 5 registrations per 5 minutes
}
_FALLBACK_LIMIT = (5, 60)  # 5 attempts per minute per IP when Redis is unavailable.
_FALLBACK_CACHE_SIZE = 10_000


def _get_client_ip(request: Request) -> str:
    """Extract client IP, respecting X-Forwarded-For behind a proxy."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    client = request.client
    return client.host if client else "unknown"


def _get_redis() -> object | None:
    """Lazy-connect to Redis. Returns None if unavailable."""
    try:
        import redis as redis_lib

        url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        return redis_lib.Redis.from_url(url, decode_responses=True, socket_timeout=1)
    except Exception:
        logger.debug("Rate limiter: Redis unavailable, skipping")
        return None


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Sliding window rate limiter for sensitive endpoints."""

    def __init__(self, app: object) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self._redis: object | None = None
        self._redis_checked = False
        self._fallback_cache: TTLCache[str, deque[float]] = TTLCache(
            maxsize=_FALLBACK_CACHE_SIZE,
            ttl=_FALLBACK_LIMIT[1],
        )
        self._fallback_lock = Lock()

    def _ensure_redis(self) -> object | None:
        if not self._redis_checked:
            self._redis = _get_redis()
            self._redis_checked = True
        return self._redis

    def _too_many_requests_response(self, retry_after: int) -> JSONResponse:
        return JSONResponse(
            status_code=429,
            content={
                "code": "rate_limit_exceeded",
                "message": "Too many requests. Please try again later.",
                "details": None,
            },
            headers={"Retry-After": str(retry_after)},
        )

    def _check_fallback_limit(
        self, client_ip: str, clean_path: str, now: float
    ) -> tuple[bool, int, int]:
        """Fallback in-memory sliding window: (allowed, remaining, reset_or_retry)."""
        max_requests, window_seconds = _FALLBACK_LIMIT
        key = f"rate_limit:fallback:{clean_path}:{client_ip}"

        with self._fallback_lock:
            window = self._fallback_cache.get(key)
            if window is None:
                window = deque()

            cutoff = now - window_seconds
            while window and window[0] <= cutoff:
                window.popleft()

            if len(window) >= max_requests:
                retry_after = max(1, int(window[0] + window_seconds - now))
                self._fallback_cache[key] = window
                return False, 0, retry_after

            window.append(now)
            self._fallback_cache[key] = window
            remaining = max(0, max_requests - len(window))
            reset_at = int(window[0] + window_seconds)
            return True, remaining, reset_at

    async def _dispatch_with_fallback(
        self,
        request: Request,
        call_next: object,
        client_ip: str,
        clean_path: str,
        now: float,
    ) -> Response:
        allowed, remaining, reset_or_retry = self._check_fallback_limit(
            client_ip, clean_path, now
        )
        if not allowed:
            logger.warning(
                "Rate limit exceeded (fallback): %s on %s (%d/%d)",
                client_ip,
                clean_path,
                _FALLBACK_LIMIT[0],
                _FALLBACK_LIMIT[0],
            )
            return self._too_many_requests_response(reset_or_retry)

        response: Response = await call_next(request)  # type: ignore[call-arg]
        response.headers["X-RateLimit-Limit"] = str(_FALLBACK_LIMIT[0])
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(reset_or_retry)
        return response

    async def dispatch(self, request: Request, call_next: object) -> Response:
        # Only rate-limit POST requests to auth paths
        if request.method != "POST":
            return await call_next(request)  # type: ignore[call-arg]

        path = request.url.path
        # Also check /api/v1 prefixed versions
        clean_path = path.replace("/api/v1", "", 1) if path.startswith("/api/v1") else path

        config = _RATE_LIMIT_PATHS.get(clean_path)
        if not config:
            return await call_next(request)  # type: ignore[call-arg]

        max_requests, window_seconds = config
        client_ip = _get_client_ip(request)
        now = time.time()
        r = self._ensure_redis()
        if r is None:
            return await self._dispatch_with_fallback(
                request, call_next, client_ip, clean_path, now
            )

        key = f"rate_limit:{clean_path}:{client_ip}"

        try:
            pipe = r.pipeline()  # type: ignore[union-attr]
            # Remove expired entries
            pipe.zremrangebyscore(key, 0, now - window_seconds)
            # Count remaining entries
            pipe.zcard(key)
            # Add current request
            pipe.zadd(key, {str(now): now})
            # Set expiry on the key
            pipe.expire(key, window_seconds)
            results = pipe.execute()
            current_count = results[1]
        except Exception as exc:
            logger.warning(
                "Rate limiter: Redis error (%s), using fallback",
                exc.__class__.__name__,
            )
            return await self._dispatch_with_fallback(
                request, call_next, client_ip, clean_path, now
            )

        if current_count >= max_requests:
            logger.warning(
                "Rate limit exceeded: %s on %s (%d/%d)",
                client_ip,
                clean_path,
                current_count,
                max_requests,
            )
            return self._too_many_requests_response(window_seconds)

        response: Response = await call_next(request)  # type: ignore[call-arg]

        # Add rate limit headers for transparency
        remaining = max(0, max_requests - current_count - 1)
        response.headers["X-RateLimit-Limit"] = str(max_requests)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(int(now + window_seconds))

        return response
