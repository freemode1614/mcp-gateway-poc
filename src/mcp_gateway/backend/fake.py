"""In-memory BackendConnection for tests. No SDK or I/O involved."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from mcp import types as mcp_types

from .connection import BackendConnection, BackendState
from .stdio import BackendStartupError


@dataclass
class _ScriptedBehavior:
    call_tool_result: mcp_types.CallToolResult | None = None
    read_resource_result: mcp_types.ReadResourceResult | None = None
    raise_on_start: Exception | None = None
    raise_on_call_tool: Exception | None = None


@dataclass
class FakeBackendConnection:
    """Configurable in-memory backend for unit/integration tests.

    Pre-populate `tools` and `resources` to simulate an MCP backend. Override
    `raise_on_*` fields to inject failures. Implements the BackendConnection protocol.
    """

    name: str
    tools: list[mcp_types.Tool] = field(default_factory=list)
    resources: list[mcp_types.Resource] = field(default_factory=list)
    call_tool_result: mcp_types.CallToolResult | None = None
    read_resource_result: mcp_types.ReadResourceResult | None = None
    raise_on_start: Exception | None = None
    raise_on_call_tool: Exception | None = None
    raise_on_read_resource: Exception | None = None
    _state: BackendState = field(default=BackendState.UNHEALTHY, init=False)
    start_count: int = field(default=0, init=False)
    stop_count: int = field(default=0, init=False)
    call_log: list[tuple[str, dict[str, Any]]] = field(default_factory=list, init=False)
    read_log: list[str] = field(default_factory=list, init=False)

    @property
    def state(self) -> BackendState:
        return self._state

    async def start(self) -> None:
        self.start_count += 1
        if self.raise_on_start is not None:
            self._state = BackendState.UNHEALTHY
            raise BackendStartupError(str(self.raise_on_start)) from self.raise_on_start
        self._state = BackendState.HEALTHY

    async def stop(self) -> None:
        self.stop_count += 1
        self._state = BackendState.UNHEALTHY

    async def healthcheck(self) -> bool:
        return self._state == BackendState.HEALTHY

    async def list_tools(self) -> list[mcp_types.Tool]:
        return list(self.tools)

    async def call_tool(
        self, name: str, arguments: dict[str, Any]
    ) -> mcp_types.CallToolResult:
        self.call_log.append((name, arguments))
        if self.raise_on_call_tool is not None:
            raise self.raise_on_call_tool
        if self.call_tool_result is not None:
            return self.call_tool_result
        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(type="text", text="ok")],
            isError=False,
        )

    async def list_resources(self) -> list[mcp_types.Resource]:
        return list(self.resources)

    async def read_resource(self, uri: str) -> mcp_types.ReadResourceResult:
        self.read_log.append(uri)
        if self.raise_on_read_resource is not None:
            raise self.raise_on_read_resource
        if self.read_resource_result is not None:
            return self.read_resource_result
        return mcp_types.ReadResourceResult(
            contents=[
                mcp_types.TextResourceContents(
                    uri=uri, mimeType="text/plain", text="ok"
                )
            ]
        )


__all__ = ["FakeBackendConnection"]
