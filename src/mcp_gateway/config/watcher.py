"""File watcher for hot-reloading the gateway config."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TYPE_CHECKING

from watchfiles import Change, awatch

from ..observability import get_logger

if TYPE_CHECKING:
    from . import GatewayConfig

logger = get_logger(__name__)

OnChangeCallback = Callable[["GatewayConfig"], Awaitable[None]]


class ConfigWatcher:
    """Watch a config file and call `on_change(new_config)` on debounced changes.

    Debouncing strategy: a change sets a "dirty" flag and a timer. The apply task
    waits for `debounce_s` of silence before reloading, collapsing editor bursts
    into a single reload.
    """

    def __init__(
        self,
        *,
        config_path: Path,
        debounce_ms: int = 500,
        on_change: OnChangeCallback,
    ) -> None:
        self._config_path = config_path
        self._debounce_s = debounce_ms / 1000.0
        self._on_change = on_change
        self._task: asyncio.Task[None] | None = None
        self._stop_event: asyncio.Event | None = None
        self._dirty_event = asyncio.Event()

    async def start(self) -> None:
        if self._task is not None:
            raise RuntimeError("ConfigWatcher already started")
        self._stop_event = asyncio.Event()
        self._task = asyncio.create_task(self._run(), name="config-watcher")

    async def stop(self) -> None:
        if self._stop_event is not None:
            self._stop_event.set()
        self._dirty_event.set()
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=2.0)
            except (TimeoutError, asyncio.CancelledError):
                self._task.cancel()
            self._task = None
        self._stop_event = None

    async def _run(self) -> None:
        assert self._stop_event is not None
        watch_task = asyncio.create_task(self._watch_loop(), name="config-watcher-fswatch")
        debounce_task = asyncio.create_task(self._debounce_loop(), name="config-watcher-debounce")
        try:
            done, _ = await asyncio.wait(
                {watch_task, debounce_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            for t in done:
                if t.cancelled():
                    continue
                exc = t.exception()
                if exc is not None:
                    raise exc
        finally:
            for t in (watch_task, debounce_task):
                if not t.done():
                    t.cancel()
                    try:
                        await t
                    except (asyncio.CancelledError, Exception):
                        pass

    async def _watch_loop(self) -> None:
        assert self._stop_event is not None
        stop_event = self._stop_event
        async for changes in awatch(self._config_path, stop_event=stop_event):
            if not any(change != Change.deleted for change, _ in changes):
                continue
            self._dirty_event.set()

    async def _debounce_loop(self) -> None:
        assert self._stop_event is not None
        stop_event = self._stop_event
        while not stop_event.is_set():
            try:
                await asyncio.wait_for(
                    self._dirty_event.wait(),
                    timeout=self._debounce_s if self._debounce_s > 0 else 0.05,
                )
            except TimeoutError:
                continue
            if stop_event.is_set():
                return
            # Drain a debounce window of "silence" by clearing and waiting again.
            self._dirty_event.clear()
            if self._debounce_s > 0:
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=self._debounce_s)
                    return
                except TimeoutError:
                    pass
            if stop_event.is_set():
                return
            if self._dirty_event.is_set():
                # More changes arrived during the wait; restart debounce cycle.
                continue
            await self._apply()

    async def _apply(self) -> None:
        from . import load_config  # local import avoids circular at module load

        try:
            new_config = await asyncio.to_thread(load_config, self._config_path)
        except Exception as exc:
            logger.error("config_error", error=str(exc), path=str(self._config_path))
            return
        try:
            await self._on_change(new_config)
        except Exception as exc:
            logger.error("reload_callback_error", error=str(exc))


__all__ = ["ConfigWatcher"]
