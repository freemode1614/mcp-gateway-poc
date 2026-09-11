"""Router: dispatch tools/call and resources/read to the owning backend."""

from __future__ import annotations

from typing import Any

from mcp import types as mcp_types

from ..backend import (
    BackendConnection,
    BackendUnavailableError,
    ToolCallError,
    UnknownToolError,
)
from .registry import Registry


class Router:
    def __init__(self, registry: Registry, get_backend: Any) -> None:
        self._registry = registry
        self._get_backend = get_backend

    async def dispatch_tool_call(
        self, prefixed_name: str, arguments: dict[str, Any]
    ) -> mcp_types.CallToolResult:
        entry = self._registry.lookup_tool(prefixed_name)
        if entry is None:
            raise UnknownToolError(prefixed_name)
        backend = await self._resolve_backend(entry.backend_name)
        try:
            return await backend.call_tool(entry.real_name, arguments)
        except Exception as exc:
            raise ToolCallError(
                backend=entry.backend_name, tool=entry.real_name, message=str(exc)
            ) from exc

    async def dispatch_resource_read(self, prefixed_uri: str) -> mcp_types.ReadResourceResult:
        entry = self._registry.lookup_resource(prefixed_uri)
        if entry is None:
            raise UnknownToolError(prefixed_uri)
        backend = await self._resolve_backend(entry.backend_name)
        try:
            return await backend.read_resource(entry.real_name)
        except Exception as exc:
            raise ToolCallError(
                backend=entry.backend_name, tool=entry.real_name, message=str(exc)
            ) from exc

    async def _resolve_backend(self, name: str) -> BackendConnection:
        backend = self._get_backend(name)
        if backend is None:
            raise BackendUnavailableError(name)
        if not await backend.healthcheck():
            raise BackendUnavailableError(name)
        return backend


__all__ = ["Router"]
