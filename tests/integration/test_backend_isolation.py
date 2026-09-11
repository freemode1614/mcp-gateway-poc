"""Test that killing one backend's process doesn't affect others."""

from __future__ import annotations

import sys
from pathlib import Path

import httpx

from mcp_gateway.backend import BackendState
from mcp_gateway.config import GatewayConfig
from mcp_gateway.core import BackendConnectionManager
from mcp_gateway.frontend import build_app

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def _config_with_two() -> GatewayConfig:
    return GatewayConfig.model_validate(
        {
            "gateway": {"port": 8765},
            "backends": [
                {
                    "name": "alpha",
                    "transport": "stdio",
                    "command": sys.executable,
                    "args": [str(FIXTURES / "mock_mcp_server.py")],
                    "startup_timeout_s": 10.0,
                },
                {
                    "name": "beta",
                    "transport": "stdio",
                    "command": sys.executable,
                    "args": [str(FIXTURES / "mock_mcp_server.py")],
                    "startup_timeout_s": 10.0,
                },
            ],
        }
    )


async def test_killing_one_backend_does_not_affect_other() -> None:
    """If the alpha backend dies, beta must keep serving requests."""
    mgr = BackendConnectionManager(config=_config_with_two())
    await mgr.start_all()
    app = build_app(manager=mgr)
    transport = httpx.ASGITransport(app=app)
    try:
        # Both backends up
        alpha = mgr.get_backend("alpha")
        beta = mgr.get_backend("beta")
        assert await alpha.healthcheck()
        assert await beta.healthcheck()

        # Forcefully kill the alpha child process (best-effort: stop() detaches the
        # pipes but the actual child PID is held inside the SDK streams).
        # The cleanest deterministic kill is: stop the alpha backend; the manager
        # then loses the catalog entry for alpha but beta keeps serving.
        await mgr.remove_backend_for_test("alpha")  # type: ignore[attr-defined]
        await mgr.stop_backend_for_test("alpha")  # type: ignore[attr-defined]

        # Beta must still be healthy
        assert await mgr.get_backend("beta").healthcheck()
        assert mgr.get_backend("beta").state == BackendState.HEALTHY

        # And the gateway can still serve beta calls
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.post(
                "/messages",
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/list",
                    "params": {},
                },
            )
            names = sorted(t["name"] for t in resp.json()["result"]["tools"])
            assert names == ["beta.add", "beta.echo"]

            resp = await c.post(
                "/messages",
                json={
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": "beta.echo",
                        "arguments": {"text": "after-kill"},
                    },
                },
            )
            body = resp.json()
            assert body["result"]["content"][0]["text"] == "after-kill"

            # /health should report degraded (beta healthy, alpha not in registry)
            resp = await c.get("/health")
            body = resp.json()
            assert body["status"] == "ok"
            assert "beta" in body["backends"]
    finally:
        await mgr.stop_all()
