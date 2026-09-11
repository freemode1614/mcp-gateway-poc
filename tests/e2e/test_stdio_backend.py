"""End-to-end tests: spawn real stdio MCP backends through the gateway."""

from __future__ import annotations

import sys
from pathlib import Path

import httpx

from mcp_gateway.config import GatewayConfig
from mcp_gateway.core import BackendConnectionManager
from mcp_gateway.frontend import build_app

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def _config(backends: list[dict]) -> GatewayConfig:
    return GatewayConfig.model_validate({"gateway": {"port": 8765}, "backends": backends})


async def test_stdio_backend_end_to_end() -> None:
    cfg = _config(
        [
            {
                "name": "mock",
                "transport": "stdio",
                "command": sys.executable,
                "args": [str(FIXTURES / "mock_mcp_server.py")],
                "startup_timeout_s": 10.0,
            }
        ]
    )
    mgr = BackendConnectionManager(config=cfg)
    await mgr.start_all()
    try:
        assert mgr.get_backend("mock") is not None
        healthy = await mgr.get_backend("mock").healthcheck()
        assert healthy

        tool_names = sorted(e.prefixed_name for e in mgr.registry.list_tools())
        assert tool_names == ["mock.add", "mock.echo"]

        app = build_app(manager=mgr)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.post(
                "/messages",
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {
                        "name": "mock.add",
                        "arguments": {"a": 2, "b": 3},
                    },
                },
            )
            body = resp.json()
            assert "result" in body, body
            assert body["result"]["content"][0]["text"] == "5.0"

            resp = await c.post(
                "/messages",
                json={
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": "mock.echo",
                        "arguments": {"text": "hi"},
                    },
                },
            )
            body = resp.json()
            assert body["result"]["content"][0]["text"] == "hi"
    finally:
        await mgr.stop_all()


async def test_resources_end_to_end() -> None:
    cfg = _config(
        [
            {
                "name": "mock",
                "transport": "stdio",
                "command": sys.executable,
                "args": [str(FIXTURES / "mock_mcp_server.py")],
                "startup_timeout_s": 10.0,
            }
        ]
    )
    mgr = BackendConnectionManager(config=cfg)
    await mgr.start_all()
    try:
        app = build_app(manager=mgr)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.post(
                "/messages",
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "resources/list",
                    "params": {},
                },
            )
            uris = [r["uri"] for r in resp.json()["result"]["resources"]]
            assert any("mock://" in u for u in uris)

            prefixed = next(u for u in uris if "hello" in u)
            resp = await c.post(
                "/messages",
                json={
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "resources/read",
                    "params": {"uri": prefixed},
                },
            )
            body = resp.json()
            assert "result" in body
            assert body["result"]["contents"][0]["text"] == "hello world"
    finally:
        await mgr.stop_all()
