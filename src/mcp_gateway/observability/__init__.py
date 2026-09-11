"""Structured logging and observability primitives."""

from __future__ import annotations

import io
import sys
from collections.abc import MutableMapping
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any

import httpx2
import structlog

from .metrics import (
    Counter,
    MetricsRegistry,
    get_metrics,
    record_backend_request,
    record_tool_call,
)

if TYPE_CHECKING:
    pass

_request_id_var: ContextVar[str | None] = ContextVar("mcp_gateway_request_id", default=None)


def set_request_id(value: str | None) -> None:
    _request_id_var.set(value)


def get_request_id() -> str | None:
    return _request_id_var.get()


def _add_request_id(
    _logger: Any, _method: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    rid = get_request_id()
    if rid is not None:
        event_dict.setdefault("request_id", rid)
    return event_dict


class _DynamicStdout(io.TextIOBase):
    """Always reads sys.stdout at write-time to dodge pytest capture swaps."""

    def writable(self) -> bool:
        return True

    def write(self, data: str) -> int:
        stream = sys.stdout
        try:
            stream.write(data)
            stream.flush()
        except (ValueError, AttributeError):
            pass
        return len(data)


_CONFIGURED = False


def configure_logging(level: str = "info") -> None:
    """Configure structlog to emit one JSON object per line to stdout."""
    global _CONFIGURED
    import logging as _logging

    log_level = getattr(_logging, level.upper(), _logging.INFO)

    stdout: io.TextIOBase = _DynamicStdout()
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            _add_request_id,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=stdout),  # ty: ignore[invalid-argument-type]
        cache_logger_on_first_use=True,
    )
    _CONFIGURED = True


def get_logger(name: str | None = None) -> Any:
    if not _CONFIGURED:
        configure_logging("info")
    return structlog.get_logger(name) if name else structlog.get_logger()


def create_mcp_http_client(
    headers: dict[str, str] | None = None,
    timeout: httpx2.Timeout | None = None,
    auth: httpx2.Auth | None = None,
) -> httpx2.AsyncClient:
    """Create an httpx2 AsyncClient with ``trust_env=False``.

    The upstream MCP SDK's ``create_mcp_http_client`` uses the default
    ``trust_env=True`` which causes httpx2 to honor system proxy settings.
    On systems with a local proxy (e.g. ClashX on 127.0.0.1:7890) this
    silently routes MCP traffic through the proxy, producing confusing 502
    errors for what should be a direct local connection.

    This factory forces ``trust_env=False`` so all HTTP connections bypass
    system/environment proxy settings.
    """
    if timeout is None:
        timeout = httpx2.Timeout(30, read=300)
    kwargs: dict[str, Any] = {"timeout": timeout, "trust_env": False}
    if headers is not None:
        kwargs["headers"] = headers
    if auth is not None:
        kwargs["auth"] = auth
    return httpx2.AsyncClient(**kwargs)


__all__ = [
    "Counter",
    "MetricsRegistry",
    "configure_logging",
    "create_mcp_http_client",
    "get_logger",
    "get_metrics",
    "get_request_id",
    "record_backend_request",
    "record_tool_call",
    "set_request_id",
]
