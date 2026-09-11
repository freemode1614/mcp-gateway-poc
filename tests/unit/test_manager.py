"""Tests for the BackendConnectionManager: lifecycle and hot reload."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mcp_gateway.backend import BackendState, FakeBackendConnection
from mcp_gateway.config import GatewayConfig
from mcp_gateway.core import BackendConnectionManager


def _config(backends: list[Any]) -> GatewayConfig:
    return GatewayConfig.model_validate(
        {
            "gateway": {"host": "127.0.0.1", "port": 8765, "log_level": "info"},
            "backends": backends,
        }
    )


async def test_manager_starts_and_registers_backends() -> None:
    fakes = {
        "github": FakeBackendConnection(
            name="github",
            tools=[
                __import__("mcp").types.Tool(
                    name="create_issue",
                    description="d",
                    inputSchema={"type": "object"},
                )
            ],
        ),
        "jira": FakeBackendConnection(name="jira"),
    }
    factory = lambda cfg: fakes[cfg.name]  # noqa: E731
    cfg = _config(
        [
            {"name": "github", "transport": "stdio", "command": "x"},
            {"name": "jira", "transport": "stdio", "command": "y"},
        ]
    )
    mgr = BackendConnectionManager(config=cfg, backend_factory=factory)
    await mgr.start_all()
    assert set(b.name for b in mgr.list_backends()) == {"github", "jira"}
    prefixed = sorted(e.prefixed_name for e in mgr.registry.list_tools())
    assert prefixed == ["github.create_issue"]
    await mgr.stop_all()
    assert mgr.list_backends() == []


async def test_manager_starts_failed_backend_and_marks_unhealthy() -> None:
    fake = FakeBackendConnection(name="bad", raise_on_start=RuntimeError("nope"))
    cfg = _config([{"name": "bad", "transport": "stdio", "command": "x"}])
    mgr = BackendConnectionManager(config=cfg, backend_factory=lambda c: fake)
    await mgr.start_all()
    assert len(mgr.list_backends()) == 1
    assert mgr.get_backend("bad").state == BackendState.UNHEALTHY
    assert mgr.registry.list_tools() == []


async def test_reload_adds_new_backend(tmp_path: Path) -> None:
    cfg = _config([{"name": "github", "transport": "stdio", "command": "x"}])
    mgr = BackendConnectionManager(
        config=cfg, backend_factory=lambda c: FakeBackendConnection(name=c.name)
    )
    await mgr.start_all()
    assert {b.name for b in mgr.list_backends()} == {"github"}

    new_cfg = _config(
        [
            {"name": "github", "transport": "stdio", "command": "x"},
            {"name": "jira", "transport": "stdio", "command": "y"},
        ]
    )
    await mgr.reload(new_cfg)
    assert {b.name for b in mgr.list_backends()} == {"github", "jira"}


async def test_reload_removes_backend() -> None:
    cfg = _config(
        [
            {"name": "github", "transport": "stdio", "command": "x"},
            {"name": "jira", "transport": "stdio", "command": "y"},
        ]
    )
    mgr = BackendConnectionManager(
        config=cfg, backend_factory=lambda c: FakeBackendConnection(name=c.name)
    )
    await mgr.start_all()
    assert {b.name for b in mgr.list_backends()} == {"github", "jira"}

    new_cfg = _config([{"name": "github", "transport": "stdio", "command": "x"}])
    await mgr.reload(new_cfg)
    assert {b.name for b in mgr.list_backends()} == {"github"}


async def test_reload_modifies_backend_by_restarting() -> None:
    fake = FakeBackendConnection(name="github")
    cfg = _config([{"name": "github", "transport": "stdio", "command": "x"}])
    mgr = BackendConnectionManager(config=cfg, backend_factory=lambda c: fake)
    await mgr.start_all()
    assert fake.start_count == 1

    new_cfg = _config([{"name": "github", "transport": "stdio", "command": "y"}])
    await mgr.reload(new_cfg)
    # Modified -> stop+start, so fake.start_count incremented.
    assert fake.stop_count == 1
    assert fake.start_count == 2


async def test_reload_keeps_unchanged_backend_alive() -> None:
    fake = FakeBackendConnection(name="github")
    cfg = _config([{"name": "github", "transport": "stdio", "command": "x"}])
    mgr = BackendConnectionManager(config=cfg, backend_factory=lambda c: fake)
    await mgr.start_all()
    same_cfg = _config([{"name": "github", "transport": "stdio", "command": "x"}])
    await mgr.reload(same_cfg)
    assert fake.start_count == 1
    assert fake.stop_count == 0


async def test_reload_partial_failure_does_not_roll_back_others() -> None:
    cfg = _config([{"name": "github", "transport": "stdio", "command": "x"}])
    mgr = BackendConnectionManager(
        config=cfg,
        backend_factory=lambda c: (
            FakeBackendConnection(name=c.name)
            if c.name == "github"
            else FakeBackendConnection(name=c.name, raise_on_start=RuntimeError("fail"))
        ),
    )
    await mgr.start_all()
    assert {b.name for b in mgr.list_backends()} == {"github"}

    new_cfg = _config(
        [
            {"name": "github", "transport": "stdio", "command": "x"},
            {"name": "jira", "transport": "stdio", "command": "y"},
        ]
    )
    await mgr.reload(new_cfg)
    # github still healthy; jira tracked but unhealthy
    names = {b.name for b in mgr.list_backends()}
    assert names == {"github", "jira"}
    assert mgr.get_backend("github").state == BackendState.HEALTHY
    assert mgr.get_backend("jira").state == BackendState.UNHEALTHY


async def test_reload_sse_header_change_restarts() -> None:
    fake = FakeBackendConnection(name="github")
    cfg = _config(
        [
            {
                "name": "github",
                "transport": "sse",
                "url": "http://127.0.0.1:9001/sse",
                "headers": {"Authorization": "Bearer a"},
            }
        ]
    )
    mgr = BackendConnectionManager(config=cfg, backend_factory=lambda c: fake)
    await mgr.start_all()

    new_cfg = _config(
        [
            {
                "name": "github",
                "transport": "sse",
                "url": "http://127.0.0.1:9001/sse",
                "headers": {"Authorization": "Bearer b"},
            }
        ]
    )
    await mgr.reload(new_cfg)
    assert fake.stop_count == 1
    assert fake.start_count == 2
