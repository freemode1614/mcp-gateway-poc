"""E2E test: HttpSseBackend connecting to a real SSE MCP server."""

from __future__ import annotations

import asyncio
import socket
import sys
import time
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


async def _wait_for_port(port: int, timeout: float = 5.0) -> None:
    started = time.monotonic()
    while time.monotonic() - started < timeout:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return
        except OSError:
            await asyncio.sleep(0.05)
    raise TimeoutError(f"port {port} did not open within {timeout}s")


async def test_sse_backend_end_to_end() -> None:
    port = _free_port()
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        str(FIXTURES / "sse_mock_server.py"),
        str(port),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        await _wait_for_port(port, timeout=10.0)

        cfg = GatewayConfig.model_validate(
            {
                "gateway": {"port": 8765},
                "backends": [
                    {
                        "name": "remote",
                        "transport": "sse",
                        "url": f"http://127.0.0.1:{port}/sse",
                        "startup_timeout_s": 10.0,
                    }
                ],
            }
        )
        mgr = BackendConnectionManager(config=cfg)
        await mgr.start_all()
        try:
            backend = mgr.get_backend("remote")
            assert backend is not None
            assert await backend.healthcheck()
            names = sorted(e.prefixed_name for e in mgr.registry.list_tools())
            assert names == ["remote.sse_add", "remote.sse_echo"]

            app = build_app(manager=mgr)
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://test"
            ) as c:
                resp = await c.post(
                    "/messages",
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "tools/call",
                        "params": {
                            "name": "remote.sse_echo",
                            "arguments": {"text": "via-sse"},
                        },
                    },
                )
                body = resp.json()
                assert "result" in body, body
                assert body["result"]["content"][0]["text"] == "via-sse"

                resp = await c.post(
                    "/messages",
                    json={
                        "jsonrpc": "2.0",
                        "id": 2,
                        "method": "tools/call",
                        "params": {
                            "name": "remote.sse_add",
                            "arguments": {"a": 7, "b": 3},
                        },
                    },
                )
                body = resp.json()
                assert body["result"]["content"][0]["text"] == "10.0"

                resp = await c.post(
                    "/messages",
                    json={
                        "jsonrpc": "2.0",
                        "id": 3,
                        "method": "resources/list",
                        "params": {},
                    },
                )
                uris = [r["uri"] for r in resp.json()["result"]["resources"]]
                assert any("remote://" in u and "greeting" in u for u in uris)
        finally:
            await mgr.stop_all()
    finally:
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=3.0)
        except (TimeoutError, asyncio.CancelledError):
            proc.kill()
            await proc.wait()
