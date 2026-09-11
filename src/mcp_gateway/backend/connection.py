"""Common abstractions for backend connections."""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from mcp import types as mcp_types


class BackendState(enum.StrEnum):
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    PERMANENTLY_FAILED = "permanently_failed"


@dataclass(frozen=True)
class BackendStatus:
    name: str
    state: BackendState
    detail: str = ""


class UnknownToolError(Exception):
    """The prefixed tool name is not present in any registered backend."""

    def __init__(self, prefixed_name: str) -> None:
        super().__init__(f"unknown tool {prefixed_name!r}")
        self.prefixed_name = prefixed_name


class BackendUnavailableError(Exception):
    """The backend owning the requested resource is not currently healthy."""

    def __init__(self, backend_name: str) -> None:
        super().__init__(f"backend {backend_name!r} is unavailable")
        self.backend_name = backend_name


class ToolCallError(Exception):
    """Wraps a backend-side MCP error so the frontend can surface it as JSON-RPC."""

    def __init__(self, backend: str, tool: str, message: str) -> None:
        super().__init__(f"backend {backend!r} tool {tool!r} failed: {message}")
        self.backend = backend
        self.tool = tool
        self.message = message


@runtime_checkable
class BackendConnection(Protocol):
    """Unified interface implemented by every backend transport."""

    @property
    def name(self) -> str: ...

    @property
    def state(self) -> BackendState: ...

    async def start(self) -> None:
        """Open transport, run MCP initialize, populate internal catalogs."""
        ...

    async def stop(self) -> None:
        """Tear down transport and free resources. Idempotent."""
        ...

    async def healthcheck(self) -> bool:
        """Return True if the backend can currently serve requests."""
        ...

    async def list_tools(self) -> list[mcp_types.Tool]:
        """Return the backend's tools with their native names (no prefix)."""
        ...

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> mcp_types.CallToolResult:
        """Invoke a tool on this backend using the backend-native name."""
        ...

    async def list_resources(self) -> list[mcp_types.Resource]:
        """Return the backend's resources with their native URIs (no prefix)."""
        ...

    async def read_resource(self, uri: str) -> mcp_types.ReadResourceResult:
        """Read a resource using the backend-native URI (no prefix)."""
        ...


__all__ = [
    "BackendConnection",
    "BackendState",
    "BackendStatus",
    "BackendUnavailableError",
    "ToolCallError",
    "UnknownToolError",
]
