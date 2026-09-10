"""Request-ID propagation middleware."""

from __future__ import annotations

import re
import time
from typing import Awaitable, Callable

import uuid
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from ..observability import get_logger, set_request_id

logger = get_logger(__name__)

_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._\-]{1,128}$")
_GENERATED_PREFIX = "req_"


def _new_request_id() -> str:
    return _GENERATED_PREFIX + uuid.uuid4().hex[:8]


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        incoming = request.headers.get("X-Request-ID")
        if incoming and _REQUEST_ID_PATTERN.fullmatch(incoming):
            request_id = incoming
        else:
            request_id = _new_request_id()
        set_request_id(request_id)
        started = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            set_request_id(None)
        response.headers["X-Request-ID"] = request_id
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        logger.info(
            "http_request",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=duration_ms,
            client_ip=request.client.host if request.client else None,
        )
        return response


__all__ = ["RequestIDMiddleware"]
