"""Lifecycle manager for backend connections, with hot-reload diff and restart policy."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Callable

from ..backend import (
    BackendConnection,
    BackendState,
    FakeBackendConnection,
    HttpSseBackend,
    StdioBackend,
)
from ..backend.stdio import BackendStartupError
from ..config import BackendConfig, GatewayConfig, SseBackendConfig, StdioBackendConfig
from ..observability import get_logger
from .registry import Registry

logger = get_logger(__name__)


@dataclass(frozen=True)
class RestartPolicy:
    max_attempts: int = 3
    backoff_schedule_s: tuple[float, ...] = (1.0, 2.0, 4.0)


class BackendConnectionManager:
    """Owns the live set of backend connections and the aggregated Registry."""

    def __init__(
        self,
        *,
        config: GatewayConfig | None = None,
        registry: Registry | None = None,
        backend_factory: Callable[[BackendConfig], BackendConnection] | None = None,
        restart_policy: RestartPolicy | None = None,
    ) -> None:
        self._registry = registry or Registry()
        self._backends: dict[str, BackendConnection] = {}
        self._configs_by_name: dict[str, BackendConfig] = {}
        self._restart_counts: dict[str, int] = {}
        self._restart_policy = restart_policy or RestartPolicy()
        self._config = config
        self._backend_factory = backend_factory or _default_backend_factory

    @property
    def registry(self) -> Registry:
        return self._registry

    def get_backend(self, name: str) -> BackendConnection | None:
        return self._backends.get(name)

    def list_backends(self) -> list[BackendConnection]:
        return list(self._backends.values())

    async def start_all(self) -> None:
        if self._config is None:
            raise RuntimeError("BackendConnectionManager.start_all called without config")
        for backend_config in self._config.backends:
            await self._add_backend(backend_config)

    async def stop_all(self) -> None:
        for name in list(self._backends.keys()):
            await self._stop_and_unregister(name)
        self._restart_counts.clear()

    async def reload(self, new_config: GatewayConfig) -> None:
        new_names = {b.name for b in new_config.backends}
        current_names = set(self._backends.keys())
        added = new_names - current_names
        removed = current_names - new_names
        common = current_names & new_names

        restarted: list[str] = []
        for name in removed:
            await self._stop_and_unregister(name)
            self._configs_by_name.pop(name, None)
            logger.info("reload_backend_removed", backend=name)

        new_by_name = {b.name: b for b in new_config.backends}
        for name in common:
            old_cfg = self._configs_by_name.get(name)
            new_cfg = new_by_name[name]
            old_sig = (
                _backend_signature_for_config(old_cfg)
                if old_cfg is not None
                else ("unknown",)
            )
            new_sig = _backend_signature_for_config(new_cfg)
            if old_sig != new_sig:
                await self._stop_and_unregister(name)
                await self._add_backend(new_cfg)
                restarted.append(name)
                logger.info("reload_backend_restarted", backend=name)
            else:
                self._restart_counts.pop(name, None)
                self._configs_by_name[name] = new_cfg

        for name in added:
            await self._add_backend(new_by_name[name])
            logger.info("reload_backend_added", backend=name)

        self._config = new_config
        logger.info(
            "reload_applied",
            added=sorted(added),
            removed=sorted(removed),
            restarted=sorted(restarted),
        )

    async def _add_backend(self, backend_config: BackendConfig) -> None:
        backend = self._backend_factory(backend_config)
        try:
            await backend.start()
        except BackendStartupError as exc:
            self._restart_counts.pop(backend.name, None)
            logger.warning("backend_start_failed", backend=backend.name, error=str(exc))
            # Track failed backends so /health can report them.
            self._backends[backend.name] = backend
            self._configs_by_name[backend.name] = backend_config
            return
        tools = await _safe_list_tools(backend)
        resources = await _safe_list_resources(backend)
        await self._registry.add_backend_tools(backend.name, tools)
        await self._registry.add_backend_resources(backend.name, resources)
        self._backends[backend.name] = backend
        self._configs_by_name[backend.name] = backend_config
        self._restart_counts.pop(backend.name, None)

    async def _stop_and_unregister(self, name: str) -> None:
        backend = self._backends.pop(name, None)
        await self._registry.remove_backend(name)
        if backend is None:
            return
        try:
            await backend.stop()
        except Exception as exc:
            logger.warning("backend_stop_error", backend=name, error=str(exc))

    async def remove_backend_for_test(self, name: str) -> None:
        """Test helper: drop a backend from the registry without stopping the
        underlying process. Used by isolation tests."""
        await self._registry.remove_backend(name)
        self._backends.pop(name, None)

    async def stop_backend_for_test(self, name: str) -> None:
        """Test helper: stop a backend's underlying transport."""
        backend = self._backends.get(name)
        if backend is not None:
            await backend.stop()


def _default_backend_factory(config: BackendConfig) -> BackendConnection:
    if isinstance(config, StdioBackendConfig):
        return StdioBackend(config)
    if isinstance(config, SseBackendConfig):
        return HttpSseBackend(config)
    raise ValueError(f"unsupported backend transport for config {config!r}")


async def _safe_list_tools(backend: BackendConnection) -> list[Any]:
    try:
        return await backend.list_tools()
    except Exception as exc:
        logger.warning("list_tools_failed", backend=backend.name, error=str(exc))
        return []


async def _safe_list_resources(backend: BackendConnection) -> list[Any]:
    try:
        return await backend.list_resources()
    except Exception as exc:
        logger.warning("list_resources_failed", backend=backend.name, error=str(exc))
        return []


def _backend_signature(backend: BackendConnection) -> tuple[Any, ...]:
    if isinstance(backend, StdioBackend):
        cfg = backend._config  # noqa: SLF001 - internal access for signature diffing
        return ("stdio", cfg.command, tuple(cfg.args), tuple(sorted(cfg.env.items())))
    if isinstance(backend, HttpSseBackend):
        cfg = backend._config  # noqa: SLF001
        return ("sse", cfg.url, tuple(sorted(cfg.headers.items())))
    if isinstance(backend, FakeBackendConnection):
        return ("fake", id(backend))
    return (type(backend).__name__,)


def _backend_signature_for_config(config: BackendConfig) -> tuple[Any, ...]:
    if isinstance(config, StdioBackendConfig):
        return ("stdio", config.command, tuple(config.args), tuple(sorted(config.env.items())))
    return ("sse", config.url, tuple(sorted(config.headers.items())))


__all__ = ["BackendConnectionManager", "BackendStartupError", "RestartPolicy"]
