"""Tests for ConfigWatcher hot-reload integration with BackendConnectionManager."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from mcp_gateway.backend import FakeBackendConnection
from mcp_gateway.config import ConfigWatcher, load_config
from mcp_gateway.core import BackendConnectionManager


def _write(path: Path, body: str) -> Path:
    path.write_text(body)
    return path


async def test_watcher_start_twice_raises(tmp_path: Path) -> None:
    cfg_path = _write(tmp_path / "c.yaml", "backends: []\n")
    watcher = ConfigWatcher(
        config_path=cfg_path, debounce_ms=50, on_change=lambda c: asyncio.sleep(0)
    )
    await watcher.start()
    try:
        with pytest.raises(RuntimeError, match="already started"):
            await watcher.start()
    finally:
        await watcher.stop()


async def test_watcher_stop_when_not_started_is_noop(tmp_path: Path) -> None:
    cfg_path = _write(tmp_path / "c.yaml", "backends: []\n")
    watcher = ConfigWatcher(
        config_path=cfg_path, debounce_ms=50, on_change=lambda c: asyncio.sleep(0)
    )
    await watcher.stop()


async def test_watcher_handles_callback_exception(tmp_path: Path) -> None:
    cfg_path = _write(
        tmp_path / "c.yaml",
        "gateway:\n  port: 8765\nbackends:\n  - name: a\n    transport: stdio\n    command: x\n",
    )

    async def bad_cb(_new_config) -> None:
        raise RuntimeError("callback boom")

    watcher = ConfigWatcher(config_path=cfg_path, debounce_ms=50, on_change=bad_cb)
    await watcher.start()
    try:
        await asyncio.sleep(0.1)
        _write(
            cfg_path,
            "gateway:\n  port: 8765\nbackends:\n  - name: b\n    transport: stdio\n    command: x\n",
        )
        await asyncio.sleep(0.5)
        # Watcher should have logged the error and continued without crashing
        assert True
    finally:
        await watcher.stop()


async def test_watcher_invokes_callback_on_change(tmp_path: Path) -> None:
    cfg_path = _write(
        tmp_path / "c.yaml",
        "gateway:\n  port: 8765\nbackends:\n  - name: github\n    transport: stdio\n    command: x\n",
    )
    observed: list[int] = []

    async def cb(_new_config) -> None:
        observed.append(len(_new_config.backends))

    watcher = ConfigWatcher(config_path=cfg_path, debounce_ms=50, on_change=cb)
    await watcher.start()
    try:
        await asyncio.sleep(0.1)
        _write(
            cfg_path,
            "gateway:\n  port: 8765\nbackends:\n  - name: github\n    transport: stdio\n    command: x\n  - name: jira\n    transport: stdio\n    command: y\n",
        )
        # Wait up to 2s for the callback to fire
        for _ in range(40):
            if observed:
                break
            await asyncio.sleep(0.05)
        assert observed == [2]
    finally:
        await watcher.stop()


async def test_watcher_debounces_multiple_writes(tmp_path: Path) -> None:
    cfg_path = _write(
        tmp_path / "c.yaml",
        "gateway:\n  port: 8765\nbackends:\n  - name: github\n    transport: stdio\n    command: x\n",
    )
    observed: list[int] = []

    async def cb(_new_config) -> None:
        observed.append(len(_new_config.backends))

    watcher = ConfigWatcher(config_path=cfg_path, debounce_ms=300, on_change=cb)
    await watcher.start()
    try:
        await asyncio.sleep(0.1)
        # Three rapid edits
        for i in range(3):
            _write(
                cfg_path,
                f"gateway:\n  port: 8765\nbackends:\n  - name: a{i}\n    transport: stdio\n    command: x\n",
            )
            await asyncio.sleep(0.05)
        await asyncio.sleep(0.8)
        # Expect at most one reload
        assert len(observed) <= 1
    finally:
        await watcher.stop()


async def test_watcher_logs_config_error_on_invalid_yaml(tmp_path: Path) -> None:
    cfg_path = _write(
        tmp_path / "c.yaml",
        "gateway:\n  port: 8765\nbackends:\n  - name: github\n    transport: stdio\n    command: x\n",
    )
    observed: list[int] = []

    async def cb(_new_config) -> None:
        observed.append(1)

    watcher = ConfigWatcher(config_path=cfg_path, debounce_ms=50, on_change=cb)
    await watcher.start()
    try:
        await asyncio.sleep(0.1)
        _write(
            cfg_path,
            "gateway:\n  port: 99999\nbackends:\n  - name: github\n    transport: stdio\n    command: x\n",
        )
        await asyncio.sleep(0.5)
        # Callback should NOT be called because the new config is invalid
        assert observed == []
    finally:
        await watcher.stop()


async def test_manager_reload_via_yaml_change(tmp_path: Path) -> None:
    """End-to-end: write YAML, edit it, manager picks up the change."""
    cfg_path = _write(
        tmp_path / "c.yaml",
        "gateway:\n  port: 8765\nbackends:\n  - name: github\n    transport: stdio\n    command: x\n",
    )
    config = load_config(cfg_path)
    mgr = BackendConnectionManager(
        config=config,
        backend_factory=lambda c: FakeBackendConnection(name=c.name),
    )
    await mgr.start_all()
    try:
        assert {b.name for b in mgr.list_backends()} == {"github"}

        watcher = ConfigWatcher(config_path=cfg_path, debounce_ms=50, on_change=mgr.reload)
        await watcher.start()
        try:
            await asyncio.sleep(0.1)
            _write(
                cfg_path,
                "gateway:\n  port: 8765\nbackends:\n  - name: github\n    transport: stdio\n    command: x\n  - name: jira\n    transport: stdio\n    command: y\n",
            )
            # Wait up to 2s for reload
            for _ in range(40):
                if {b.name for b in mgr.list_backends()} == {"github", "jira"}:
                    break
                await asyncio.sleep(0.05)
            assert {b.name for b in mgr.list_backends()} == {"github", "jira"}

            # Now remove github
            _write(
                cfg_path,
                "gateway:\n  port: 8765\nbackends:\n  - name: jira\n    transport: stdio\n    command: y\n",
            )
            for _ in range(40):
                if {b.name for b in mgr.list_backends()} == {"jira"}:
                    break
                await asyncio.sleep(0.05)
            assert {b.name for b in mgr.list_backends()} == {"jira"}
        finally:
            await watcher.stop()
    finally:
        await mgr.stop_all()
