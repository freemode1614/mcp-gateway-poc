"""Smoke test: run the gateway with a real stdio backend, hit it with httpx, verify all flows."""

from __future__ import annotations

import socket
import sys
from pathlib import Path

import httpx
import pytest

from mcp_gateway.config import GatewayConfig
from mcp_gateway.core import BackendConnectionManager
from mcp_gateway.frontend import build_app

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
async def running_gateway():
    """Build the FastAPI app with a real stdio backend and serve it via httpx ASGI."""
    cfg = GatewayConfig.model_validate(
        {
            "gateway": {"port": _free_port()},
            "backends": [
                {
                    "name": "mock",
                    "transport": "stdio",
                    "command": sys.executable,
                    "args": [str(FIXTURES / "mock_mcp_server.py")],
                    "startup_timeout_s": 10.0,
                }
            ],
        }
    )
    mgr = BackendConnectionManager(config=cfg)
    await mgr.start_all()
    app = build_app(manager=mgr)
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            yield c, mgr
    finally:
        await mgr.stop_all()


async def test_acceptance_tools_list_returns_prefixed_names(running_gateway) -> None:
    c, _mgr = running_gateway
    resp = await c.post(
        "/messages",
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
    )
    body = resp.json()
    assert "result" in body
    names = sorted(t["name"] for t in body["result"]["tools"])
    assert names == ["mock.add", "mock.echo"]


async def test_acceptance_echo_call(running_gateway) -> None:
    c, _mgr = running_gateway
    resp = await c.post(
        "/messages",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "mock.echo", "arguments": {"text": "hello"}},
        },
    )
    body = resp.json()
    assert body["result"]["content"][0]["text"] == "hello"


async def test_acceptance_add_call(running_gateway) -> None:
    c, _mgr = running_gateway
    resp = await c.post(
        "/messages",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "mock.add", "arguments": {"a": 10, "b": 32}},
        },
    )
    body = resp.json()
    assert body["result"]["content"][0]["text"] == "42.0"


async def test_acceptance_resources_read(running_gateway) -> None:
    c, mgr = running_gateway
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
    assert body["result"]["contents"][0]["text"] == "hello world"


async def test_acceptance_health(running_gateway) -> None:
    c, _mgr = running_gateway
    resp = await c.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["backends"] == {"mock": "healthy"}


async def test_acceptance_request_id_in_response_header(running_gateway) -> None:
    c, _mgr = running_gateway
    resp = await c.post(
        "/messages",
        json={"jsonrpc": "2.0", "id": 1, "method": "ping", "params": {}},
        headers={"X-Request-ID": "test-trace-12345"},
    )
    assert resp.headers["X-Request-ID"] == "test-trace-12345"
