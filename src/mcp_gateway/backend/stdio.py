"""Stdio MCP backend: spawn a child process and speak MCP over its stdin/stdout."""

from __future__ import annotations

import asyncio
import sys
from contextlib import AbstractAsyncContextManager
from typing import Any

from mcp import ClientSession
from mcp import types as mcp_types
from mcp.client.stdio import StdioServerParameters, stdio_client

from ..config import StdioBackendConfig
from ..observability import get_logger
from .connection import BackendConnection, BackendState

logger = get_logger(__name__)


class StdioBackend(BackendConnection):
    """Spawn an MCP server as a subprocess and talk to it over stdio."""

    def __init__(self, config: StdioBackendConfig) -> None:
        self._config = config
        self._state: BackendState = BackendState.UNHEALTHY
        self._session: ClientSession | None = None
        self._session_cm: AbstractAsyncContextManager[ClientSession] | None = None
        self._streams_cm: AbstractAsyncContextManager[Any] | None = None
        self._stop_event = asyncio.Event()

    @property
    def name(self) -> str:
        return self._config.name

    @property
    def state(self) -> BackendState:
        return self._state

    def _server_parameters(self) -> StdioServerParameters:
        return StdioServerParameters(
            command=self._config.command,
            args=list(self._config.args),
            env=dict(self._config.env) if self._config.env else None,
        )

    async def start(self) -> None:
        if self._session is not None:
            return
        self._stop_event.clear()
        params = self._server_parameters()
        try:
            async with asyncio.timeout(self._config.startup_timeout_s):
                self._streams_cm = stdio_client(params, errlog=sys.stderr)
                streams = await self._streams_cm.__aenter__()
        except TimeoutError as exc:
            self._state = BackendState.UNHEALTHY
            raise BackendStartupError(
                f"stdio backend {self.name!r} failed to start: timeout"
            ) from exc
        except (OSError, Exception) as exc:
            self._state = BackendState.UNHEALTHY
            raise BackendStartupError(
                f"stdio backend {self.name!r} failed to start: {exc}"
            ) from exc
        read_stream, write_stream = streams
        self._session_cm = ClientSession(read_stream, write_stream)
        try:
            async with asyncio.timeout(self._config.startup_timeout_s):
                session = await self._session_cm.__aenter__()
                await session.initialize()
        except TimeoutError as exc:
            await self._close_session()
            await self._close_streams()
            self._state = BackendState.UNHEALTHY
            raise BackendStartupError(
                f"stdio backend {self.name!r} initialize failed: timeout"
            ) from exc
        except Exception as exc:
            await self._close_session()
            await self._close_streams()
            self._state = BackendState.UNHEALTHY
            raise BackendStartupError(
                f"stdio backend {self.name!r} initialize failed: {exc}"
            ) from exc
        self._session = session
        self._state = BackendState.HEALTHY
        logger.info("backend_connected", backend=self.name, transport="stdio")

    async def stop(self) -> None:
        self._stop_event.set()
        await self._close_session()
        await self._close_streams()
        if self._state == BackendState.HEALTHY:
            logger.info("backend_disconnected", backend=self.name, transport="stdio")
        self._state = BackendState.UNHEALTHY

    async def healthcheck(self) -> bool:
        return (
            self._state == BackendState.HEALTHY
            and self._session is not None
            and not self._stop_event.is_set()
        )

    async def list_tools(self) -> list[mcp_types.Tool]:
        session = self._session_or_raise()
        result = await session.list_tools()
        return list(result.tools)

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> mcp_types.CallToolResult:
        session = self._session_or_raise()
        return await session.call_tool(name, arguments)

    async def list_resources(self) -> list[mcp_types.Resource]:
        session = self._session_or_raise()
        result = await session.list_resources()
        return list(result.resources)

    async def read_resource(self, uri: str) -> mcp_types.ReadResourceResult:
        session = self._session_or_raise()
        return await session.read_resource(uri)

    def _session_or_raise(self) -> ClientSession:
        if self._session is None or self._state != BackendState.HEALTHY:
            raise RuntimeError(f"backend {self.name!r} is not healthy")
        return self._session

    async def _close_session(self) -> None:
        if self._session_cm is not None:
            try:
                await self._session_cm.__aexit__(None, None, None)
            except Exception as exc:
                logger.warning("session_close_error", backend=self.name, error=str(exc))
            self._session_cm = None
            self._session = None

    async def _close_streams(self) -> None:
        if self._streams_cm is not None:
            try:
                await self._streams_cm.__aexit__(None, None, None)
            except Exception as exc:
                logger.warning("stdio_streams_close_error", backend=self.name, error=str(exc))
            self._streams_cm = None


class BackendStartupError(RuntimeError):
    """Raised when a backend cannot be started or fails MCP initialize."""


__all__ = ["BackendStartupError", "StdioBackend"]
