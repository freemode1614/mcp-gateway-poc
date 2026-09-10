"""HTTP/SSE MCP backend: connect to a remote MCP server over SSE."""

from __future__ import annotations

import asyncio
from typing import Any

from contextlib import AbstractAsyncContextManager
from typing import Any

from mcp import ClientSession, types as mcp_types
from mcp.client.sse import sse_client

from ..config import SseBackendConfig
from ..observability import get_logger
from .connection import BackendConnection, BackendState
from .stdio import BackendStartupError

logger = get_logger(__name__)


class HttpSseBackend(BackendConnection):
    """Connect to a remote MCP server over HTTP/SSE."""

    def __init__(self, config: SseBackendConfig) -> None:
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

    async def start(self) -> None:
        if self._session is not None:
            return
        self._stop_event.clear()
        try:
            self._streams_cm = sse_client(
                url=self._config.url,
                headers=dict(self._config.headers) if self._config.headers else None,
                timeout=self._config.startup_timeout_s,
            )
            streams = await asyncio.wait_for(
                self._streams_cm.__aenter__(),
                timeout=self._config.startup_timeout_s,
            )
        except (TimeoutError, Exception) as exc:
            self._state = BackendState.UNHEALTHY
            await self._close_streams()
            raise BackendStartupError(
                f"sse backend {self.name!r} failed to connect: {exc}"
            ) from exc
        read_stream, write_stream = streams
        self._session_cm = ClientSession(read_stream, write_stream)
        try:
            session = await asyncio.wait_for(
                self._session_cm.__aenter__(),
                timeout=self._config.startup_timeout_s,
            )
            await asyncio.wait_for(
                session.initialize(),
                timeout=self._config.startup_timeout_s,
            )
        except (TimeoutError, Exception) as exc:
            await self._close_session()
            await self._close_streams()
            self._state = BackendState.UNHEALTHY
            raise BackendStartupError(
                f"sse backend {self.name!r} initialize failed: {exc}"
            ) from exc
        self._session = session
        self._state = BackendState.HEALTHY
        logger.info(
            "backend_connected", backend=self.name, transport="sse", url=self._config.url
        )

    async def stop(self) -> None:
        self._stop_event.set()
        await self._close_session()
        await self._close_streams()
        if self._state == BackendState.HEALTHY:
            logger.info("backend_disconnected", backend=self.name, transport="sse")
        self._state = BackendState.UNHEALTHY

    async def healthcheck(self) -> bool:
        return (
            self._state == BackendState.HEALTHY
            and self._session is not None
            and not self._stop_event.is_set()
        )

    async def list_tools(self) -> list[mcp_types.Tool]:
        self._assert_healthy()
        result = await self._session.list_tools()
        return list(result.tools)

    async def call_tool(
        self, name: str, arguments: dict[str, Any]
    ) -> mcp_types.CallToolResult:
        self._assert_healthy()
        return await self._session.call_tool(name, arguments)

    async def list_resources(self) -> list[mcp_types.Resource]:
        self._assert_healthy()
        result = await self._session.list_resources()
        return list(result.resources)

    async def read_resource(self, uri: str) -> mcp_types.ReadResourceResult:
        self._assert_healthy()
        return await self._session.read_resource(uri)

    def _assert_healthy(self) -> None:
        if self._session is None or self._state != BackendState.HEALTHY:
            raise RuntimeError(f"backend {self.name!r} is not healthy")

    async def _close_session(self) -> None:
        if self._session_cm is not None:
            try:
                await self._session_cm.__aexit__(None, None, None)
            except Exception as exc:
                logger.warning(
                    "session_close_error", backend=self.name, error=str(exc)
                )
            self._session_cm = None
            self._session = None

    async def _close_streams(self) -> None:
        if self._streams_cm is not None:
            try:
                await self._streams_cm.__aexit__(None, None, None)
            except Exception as exc:
                logger.warning(
                    "sse_streams_close_error", backend=self.name, error=str(exc)
                )
            self._streams_cm = None


__all__ = ["HttpSseBackend"]
