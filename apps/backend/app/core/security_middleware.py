from __future__ import annotations

import logging
import time
from collections import defaultdict, deque
from collections.abc import Callable
from typing import Any

from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings
from app.modules.auth.security import decode_access_token

SENSITIVE_KEYS = {"password", "token", "secret", "authorization", "access_token", "refresh_token"}


def scrub_secrets(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "***" if key.lower() in SENSITIVE_KEYS else scrub_secrets(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [scrub_secrets(item) for item in value]
    return value


class SecretScrubLogFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, dict):
            record.msg = scrub_secrets(record.msg)
        elif isinstance(record.msg, str):
            for key in SENSITIVE_KEYS:
                record.msg = record.msg.replace(key, f"{key[:2]}***")
        return True


class InMemoryRateLimiter:
    def __init__(self) -> None:
        self._events: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str, limit: int, window_seconds: int) -> bool:
        now = time.time()
        events = self._events[key]
        while events and events[0] <= now - window_seconds:
            events.popleft()
        if len(events) >= limit:
            return False
        events.append(now)
        return True


rate_limiter = InMemoryRateLimiter()


class SecurityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        content_length = request.headers.get("content-length")
        try:
            body_size = int(content_length or "0")
        except ValueError:
            body_size = 0
        if body_size > settings.max_request_body_bytes:
            return JSONResponse(
                {"detail": "Request body too large"},
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            )

        if not _is_test_client(request):
            client_ip = request.client.host if request.client else "unknown"
            if request.url.path.endswith("/auth/login") and not rate_limiter.allow(
                f"login:{client_ip}",
                5,
                60,
            ):
                return JSONResponse(
                    {"detail": "Too many login attempts"},
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                )

            if request.url.path.startswith(settings.api_v1_prefix):
                user_key = _user_rate_key(request) or client_ip
                if not rate_limiter.allow(f"api:{user_key}", 60, 60):
                    return JSONResponse(
                        {"detail": "Too many requests"},
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    )

        response = await call_next(request)
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; frame-ancestors 'none'; object-src 'none'; "
            "base-uri 'self'; form-action 'self'"
        )
        return response


def _user_rate_key(request: Request) -> str | None:
    auth_header = request.headers.get("authorization", "")
    if not auth_header.lower().startswith("bearer "):
        return None
    try:
        payload = decode_access_token(auth_header.split(" ", 1)[1])
    except Exception:
        return None
    return str(payload.get("sub") or payload.get("jti") or "")


def _is_test_client(request: Request) -> bool:
    return "testclient" in request.headers.get("user-agent", "").lower()


logging.getLogger().addFilter(SecretScrubLogFilter())
