"""Tests for Router."""

from __future__ import annotations

import pytest
from mcp import types as mcp_types

from mcp_gateway.backend import (
    BackendUnavailableError,
    FakeBackendConnection,
    ToolCallError,
    UnknownToolError,
)
from mcp_gateway.core import Registry, Router


def _tool(name: str) -> mcp_types.Tool:
    return mcp_types.Tool(
        name=name,
        description="d",
        inputSchema={"type": "object", "properties": {}},
    )


async def test_dispatch_tool_call_strips_prefix_and_forwards() -> None:
    r = Registry()
    backend = FakeBackendConnection(name="github", tools=[_tool("create_issue")])
    await backend.start()
    await r.add_backend_tools("github", backend.tools)
    router = Router(r, lambda name: backend if name == "github" else None)

    result = await router.dispatch_tool_call("github.create_issue", {"title": "x"})
    assert backend.call_log == [("create_issue", {"title": "x"})]
    assert result.is_error is False


async def test_dispatch_unknown_tool_raises() -> None:
    r = Registry()
    router = Router(r, lambda name: None)
    with pytest.raises(UnknownToolError):
        await router.dispatch_tool_call("nope.tool", {})


async def test_dispatch_when_backend_missing_raises_unavailable() -> None:
    r = Registry()
    await r.add_backend_tools("github", [_tool("create_issue")])
    router = Router(r, lambda name: None)
    with pytest.raises(BackendUnavailableError):
        await router.dispatch_tool_call("github.create_issue", {})


async def test_dispatch_when_backend_unhealthy_raises_unavailable() -> None:
    r = Registry()
    backend = FakeBackendConnection(name="github", tools=[_tool("create_issue")])
    await r.add_backend_tools("github", backend.tools)
    router = Router(r, lambda name: backend)
    # backend never started -> healthcheck False
    with pytest.raises(BackendUnavailableError):
        await router.dispatch_tool_call("github.create_issue", {})


async def test_dispatch_wraps_backend_exception_in_tool_call_error() -> None:
    r = Registry()
    backend = FakeBackendConnection(
        name="github",
        tools=[_tool("create_issue")],
        raise_on_call_tool=RuntimeError("boom"),
    )
    await backend.start()
    await r.add_backend_tools("github", backend.tools)
    router = Router(r, lambda name: backend)
    with pytest.raises(ToolCallError, match="boom"):
        await router.dispatch_tool_call("github.create_issue", {})


async def test_dispatch_resource_read_strips_prefix() -> None:
    r = Registry()
    backend = FakeBackendConnection(
        name="github",
        resources=[
            mcp_types.Resource(
                uri="repo://foo/readme",
                name="readme",
                description="d",
                mimeType="text/plain",
            )
        ],
    )
    await backend.start()
    await r.add_backend_resources("github", backend.resources)
    router = Router(r, lambda name: backend)
    prefixed = r.list_resources()[0].prefixed_name
    await router.dispatch_resource_read(prefixed)
    assert backend.read_log == ["repo://foo/readme"]


async def test_dispatch_resource_read_unknown_uri_raises() -> None:
    r = Registry()
    router = Router(r, lambda name: None)
    with pytest.raises(UnknownToolError):
        await router.dispatch_resource_read("nope://x")
