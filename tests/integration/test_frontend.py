"""Tests for the FastAPI frontend: JSON-RPC dispatcher, /health, request_id middleware."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from mcp import types as mcp_types

from mcp_gateway.backend import FakeBackendConnection
from mcp_gateway.config import GatewayConfig
from mcp_gateway.core import BackendConnectionManager
from mcp_gateway.frontend import build_app


def _config(backends: list[dict[str, Any]]) -> GatewayConfig:
    return GatewayConfig.model_validate(
        {"gateway": {"port": 8765}, "backends": backends}
    )


def _make_app(backends: list[FakeBackendConnection]) -> tuple[Any, BackendConnectionManager]:
    fake_by_name = {b.name: b for b in backends}
    cfg = _config(
        [{"name": b.name, "transport": "stdio", "command": "x"} for b in backends]
    )
    mgr = BackendConnectionManager(
        config=cfg, backend_factory=lambda c: fake_by_name[c.name]
    )
    app = build_app(manager=mgr)
    return app, mgr


@pytest.fixture
async def client() -> Any:
    backends = [
        FakeBackendConnection(
            name="github",
            tools=[
                mcp_types.Tool(
                    name="create_issue",
                    description="d",
                    inputSchema={"type": "object", "properties": {"title": {"type": "string"}}},
                )
            ],
            resources=[
                mcp_types.Resource(
                    uri="repo://foo/readme",
                    name="readme",
                    description="d",
                    mimeType="text/plain",
                )
            ],
        ),
    ]
    app, mgr = _make_app(backends)
    await mgr.start_all()
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as c:
            yield c, mgr, backends
    finally:
        await mgr.stop_all()


async def test_health_returns_200_when_healthy(client: Any) -> None:
    c, _mgr, _backends = client
    resp = await c.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["backends"] == {"github": "healthy"}


async def test_initialize_returns_capabilities(client: Any) -> None:
    c, _mgr, _backends = client
    resp = await c.post(
        "/messages",
        json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["result"]["serverInfo"]["name"] == "mcp-gateway"
    assert "tools" in body["result"]["capabilities"]
    assert "resources" in body["result"]["capabilities"]


async def test_tools_list_returns_prefixed_names(client: Any) -> None:
    c, _mgr, _backends = client
    resp = await c.post(
        "/messages",
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
    )
    body = resp.json()
    names = sorted(t["name"] for t in body["result"]["tools"])
    assert names == ["github.create_issue"]


async def test_tools_call_routes_to_backend(client: Any) -> None:
    c, _mgr, backends = client
    resp = await c.post(
        "/messages",
        json={
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "github.create_issue",
                "arguments": {"title": "bug"},
            },
        },
    )
    body = resp.json()
    assert "result" in body
    assert backends[0].call_log == [("create_issue", {"title": "bug"})]


async def test_tools_call_unknown_returns_32601(client: Any) -> None:
    c, _mgr, _backends = client
    resp = await c.post(
        "/messages",
        json={
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "missing.tool", "arguments": {}},
        },
    )
    body = resp.json()
    assert body["error"]["code"] == -32601


async def test_tools_call_backend_unavailable_returns_32001() -> None:
    backend = FakeBackendConnection(name="github")
    app, mgr = _make_app([backend])
    await mgr.start_all()
    await mgr.stop_all()
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            # Add a stale registry entry manually
            await mgr.registry.add_backend_tools(
                "github",
                [mcp_types.Tool(name="x", description="d", inputSchema={"type": "object"})],
            )
            resp = await c.post(
                "/messages",
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {"name": "github.x", "arguments": {}},
                },
            )
            body = resp.json()
            assert body["error"]["code"] == -32001
    finally:
        await mgr.stop_all()


async def test_resources_list_returns_prefixed_uris(client: Any) -> None:
    c, _mgr, _backends = client
    resp = await c.post(
        "/messages",
        json={"jsonrpc": "2.0", "id": 1, "method": "resources/list", "params": {}},
    )
    body = resp.json()
    uris = [r["uri"] for r in body["result"]["resources"]]
    assert any("github://" in u for u in uris)


async def test_resources_read_routes_by_uri(client: Any) -> None:
    c, mgr, backends = client
    prefixed = mgr.registry.list_resources()[0].prefixed_name
    resp = await c.post(
        "/messages",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "resources/read",
            "params": {"uri": prefixed},
        },
    )
    body = resp.json()
    assert "result" in body
    assert backends[0].read_log == ["repo://foo/readme"]


async def test_unknown_method_returns_32601(client: Any) -> None:
    c, _mgr, _backends = client
    resp = await c.post(
        "/messages",
        json={"jsonrpc": "2.0", "id": 1, "method": "bogus/method", "params": {}},
    )
    body = resp.json()
    assert body["error"]["code"] == -32601


async def test_ping_returns_empty_object(client: Any) -> None:
    c, _mgr, _backends = client
    resp = await c.post(
        "/messages",
        json={"jsonrpc": "2.0", "id": 1, "method": "ping", "params": {}},
    )
    body = resp.json()
    assert body["result"] == {}


async def test_request_id_header_returned(client: Any) -> None:
    c, _mgr, _backends = client
    resp = await c.post(
        "/messages",
        json={"jsonrpc": "2.0", "id": 1, "method": "ping", "params": {}},
        headers={"X-Request-ID": "my-trace-123"},
    )
    assert resp.headers["X-Request-ID"] == "my-trace-123"


async def test_request_id_generated_when_absent(client: Any) -> None:
    c, _mgr, _backends = client
    resp = await c.post(
        "/messages",
        json={"jsonrpc": "2.0", "id": 1, "method": "ping", "params": {}},
    )
    rid = resp.headers["X-Request-ID"]
    assert rid.startswith("req_")
    assert len(rid) == 12


async def test_health_degraded_with_partial_backends() -> None:
    healthy = FakeBackendConnection(name="github")
    failing = FakeBackendConnection(
        name="bad", raise_on_start=RuntimeError("nope")
    )
    app, mgr = _make_app([healthy, failing])
    await mgr.start_all()
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.get("/health")
            assert resp.status_code == 200
            body = resp.json()
            assert body["status"] == "degraded"
            assert body["backends"]["github"] == "healthy"
            assert body["backends"]["bad"] == "unhealthy"
    finally:
        await mgr.stop_all()


async def test_health_down_when_all_backends_unhealthy() -> None:
    failing = FakeBackendConnection(
        name="bad", raise_on_start=RuntimeError("nope")
    )
    app, mgr = _make_app([failing])
    await mgr.start_all()
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.get("/health")
            assert resp.status_code == 503
            body = resp.json()
            assert body["status"] == "down"
    finally:
        await mgr.stop_all()
