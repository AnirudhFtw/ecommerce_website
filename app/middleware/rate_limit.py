from collections import defaultdict, deque
from threading import Lock
from time import monotonic

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Per-process API limits; use a shared gateway/Redis limiter across workers."""

    def __init__(self, app):
        super().__init__(app)
        self._events = defaultdict(deque)
        self._lock = Lock()

    async def dispatch(self, request, call_next):
        client_ip = request.client.host if request.client else "unknown"
        authentication_route = request.url.path in {
            "/auth/login", "/auth/register", "/auth/password/forgot",
            "/auth/password/reset", "/auth/verification/confirm",
        }
        limit = 10 if authentication_route else 120
        window = 60.0
        now = monotonic()
        key = (client_ip, "auth" if authentication_route else "api")
        with self._lock:
            events = self._events[key]
            while events and now - events[0] >= window:
                events.popleft()
            if len(events) >= limit:
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Too many requests; try again shortly"},
                    headers={"Retry-After": "60"},
                )
            events.append(now)
            if len(self._events) > 10000:
                for old_key in list(self._events)[:1000]:
                    old_events = self._events[old_key]
                    while old_events and now - old_events[0] >= window:
                        old_events.popleft()
                    if not old_events:
                        self._events.pop(old_key, None)
        return await call_next(request)
