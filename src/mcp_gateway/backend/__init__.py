"""Backend connection abstractions and adapters for stdio and HTTP/SSE MCP servers."""

from __future__ import annotations

from .connection import (
    BackendConnection,
    BackendState,
    BackendStatus,
    BackendUnavailableError,
    ToolCallError,
    UnknownToolError,
)
from .fake import FakeBackendConnection
from .http_sse import HttpSseBackend
from .stdio import BackendStartupError, StdioBackend

__all__ = [
    "BackendConnection",
    "BackendStartupError",
    "BackendState",
    "BackendStatus",
    "BackendUnavailableError",
    "FakeBackendConnection",
    "HttpSseBackend",
    "StdioBackend",
    "ToolCallError",
    "UnknownToolError",
]
