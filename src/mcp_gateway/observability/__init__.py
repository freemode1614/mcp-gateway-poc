"""Structured logging and observability primitives."""

from __future__ import annotations

import io
import sys
from contextvars import ContextVar
from typing import Any

import structlog

_request_id_var: ContextVar[str | None] = ContextVar("mcp_gateway_request_id", default=None)


def set_request_id(value: str | None) -> None:
    _request_id_var.set(value)


def get_request_id() -> str | None:
    return _request_id_var.get()


def _add_request_id(_logger: Any, _method: str, event_dict: dict[str, Any]) -> dict[str, Any]:
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
    log_level = getattr(sys.modules["logging"].WARNING, "WARNING", None)  # noqa
    import logging as _logging

    log_level = getattr(_logging, level.upper(), _logging.INFO)

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
        logger_factory=structlog.PrintLoggerFactory(file=_DynamicStdout()),
        cache_logger_on_first_use=True,
    )
    _CONFIGURED = True


def get_logger(name: str | None = None) -> Any:
    if not _CONFIGURED:
        configure_logging("info")
    return structlog.get_logger(name) if name else structlog.get_logger()


__all__ = [
    "configure_logging",
    "get_logger",
    "get_request_id",
    "set_request_id",
]
