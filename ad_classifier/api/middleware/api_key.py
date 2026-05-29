from __future__ import annotations

import secrets
import time
from collections import defaultdict
from collections.abc import Awaitable, Callable

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

logger = structlog.get_logger(__name__)

_PRIVATE_PREFIXES = (
    "/api/ads/upload",
    "/api/ads/{",
    "/api/jobs/",
    "/api/agent/",
    "/api/settings",
    "/api/knowledge/",
    "/api/campaigns/discover",
    "/api/campaigns/{",
    "/api/brand-profile",
    "/api/creative-panel",
)

_UNAUTHENTICATED_ROUTES = (
    "/",
    "/api/health",
    "/docs",
    "/redoc",
    "/openapi.json",
)


class _AccessTracker:
    def __init__(self) -> None:
        self._counts: dict[str, int] = defaultdict(int)
        self._last_seen: dict[str, float] = {}
        self._total: int = 0

    def record(self, client: str, path: str) -> None:
        now = time.time()
        self._counts[client] += 1
        self._last_seen[client] = client
        self._total += 1
        if self._total % 25 == 0:
            top = sorted(self._counts.items(), key=lambda x: x[1], reverse=True)[:5]
            logger.info(
                "public_api_summary",
                total_requests=self._total,
                unique_clients=len(self._counts),
                top_clients=[f"{c}: {n} reqs" for c, n in top],
            )


_tracker = _AccessTracker()


class ApiKeyMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, public_api_key: str | None = None) -> None:
        super().__init__(app)
        self._public_key = public_api_key

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        path = request.url.path

        if path in _UNAUTHENTICATED_ROUTES:
            return await call_next(request)

        if path.startswith("/api/public"):
            return await self._handle_public(request, call_next)

        if request.method in ("GET", "HEAD", "OPTIONS"):
            return await self._handle_read(request, call_next)

        return await self._handle_write(request, call_next)

    async def _handle_public(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if not self._public_key:
            return JSONResponse(
                {"detail": "public api is not enabled"},
                status_code=403,
            )

        key = request.headers.get("X-API-Key") or request.query_params.get("api_key")
        if not key:
            return JSONResponse(
                {"detail": "X-API-Key header or api_key query parameter required"},
                status_code=401,
            )

        client = request.client.host if request.client else "unknown"

        if not secrets.compare_digest(key, self._public_key):
            logger.warning(
                "public_api_invalid_key",
                path=str(request.url.path),
                client=client,
            )
            return JSONResponse(
                {"detail": "invalid api key"},
                status_code=403,
            )

        _tracker.record(client, str(request.url.path))
        logger.info(
            "public_api_access",
            method=request.method,
            path=str(request.url.path),
            client=client,
            query=str(request.query_params) if request.query_params else None,
        )

        return await call_next(request)

    async def _handle_read(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        return await call_next(request)

    async def _handle_write(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        return await call_next(request)
