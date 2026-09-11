"""In-process counters for gateway-wide request and backend metrics.

Provides a minimal, dependency-free metrics layer suitable for a single-process
gateway. Counters live in a module-level singleton so any component can record
events without dependency injection.
"""

from __future__ import annotations

# stdlib
import threading
from collections.abc import Mapping

# third-party
# (none)

# first-party
# (none — observability is a leaf module per AGENTS.md §7.2)

# relative
# (none)

__all__ = [
    "Counter",
    "MetricsRegistry",
    "get_metrics",
    "record_backend_request",
    "record_tool_call",
]


class Counter:
    """A monotonically increasing 64-bit counter.

    Counters are safe to increment from multiple threads because all mutations
    happen under a single internal lock.
    """

    def __init__(self, name: str, help_text: str = "") -> None:
        """Initialize a counter with a stable name and optional help text.

        Args:
            name: Dotted metric name (e.g. ``gateway.tool_calls.total``).
            help_text: Human-readable description, surfaced on export.
        """
        self._name = name
        self._help = help_text
        self._value = 0
        self._lock = threading.Lock()

    @property
    def name(self) -> str:
        """Return the counter's dotted name."""
        return self._name

    @property
    def help(self) -> str:
        """Return the counter's help text (may be empty)."""
        return self._help

    @property
    def value(self) -> int:
        """Return the current value without acquiring the write lock."""
        return self._value

    def inc(self, amount: int = 1) -> None:
        """Add ``amount`` to the counter.

        Args:
            amount: Non-negative integer to add. Defaults to ``1``.

        Raises:
            ValueError: If ``amount`` is negative.
        """
        if amount < 0:
            raise ValueError(f"counter {self._name!r} cannot be decremented")
        with self._lock:
            self._value += amount


class MetricsRegistry:
    """Named collection of counters with snapshot/render helpers.

    Designed for the gateway's single-process lifetime; not a full Prometheus
    client. Use ``snapshot()`` for /health and ``render_prometheus()`` for
    scrape endpoints.
    """

    def __init__(self) -> None:
        """Initialize an empty registry."""
        self._counters: dict[str, Counter] = {}
        self._lock = threading.Lock()

    def counter(self, name: str, help_text: str = "") -> Counter:
        """Return the counter named ``name``, creating it on first access.

        Args:
            name: Dotted metric name. Must be unique within this registry.
            help_text: Help text used when the counter is first created.

        Returns:
            Counter: The shared counter instance for ``name``.
        """
        with self._lock:
            existing = self._counters.get(name)
            if existing is not None:
                return existing
            created = Counter(name, help_text)
            self._counters[name] = created
            return created

    def snapshot(self) -> Mapping[str, int]:
        """Return an immutable mapping of counter name → current value.

        Returns:
            Mapping[str, int]: Point-in-time view of every registered counter.
        """
        with self._lock:
            return {name: c.value for name, c in self._counters.items()}

    def render_prometheus(self) -> str:
        """Render counters in Prometheus text exposition format.

        Returns:
            str: Multi-line exposition document, ready to serve with the
                ``text/plain; version=0.0.4`` content type.
        """
        lines: list[str] = []
        for name in sorted(self._counters):
            counter = self._counters[name]
            if counter.help:
                lines.append(f"# HELP {counter.name} {counter.help}")
            lines.append(f"# TYPE {counter.name} counter")
            lines.append(f"{counter.name} {counter.value}")
        return "\n".join(lines) + "\n"


_REGISTRY = MetricsRegistry()


def get_metrics() -> MetricsRegistry:
    """Return the process-wide metrics registry.

    Returns:
        MetricsRegistry: The singleton registry used by all callers.
    """
    return _REGISTRY


def record_tool_call(backend: str, tool: str) -> None:
    """Increment the per-tool-call counter.

    Args:
        backend: Backend name (e.g. ``"github"``).
        tool: Prefixed tool name (e.g. ``"github.create_issue"``).
    """
    _REGISTRY.counter(
        "gateway.tool_calls.total",
        "Total tool calls dispatched by the gateway",
    ).inc()
    _REGISTRY.counter(
        f"gateway.backend.{backend}.tool_calls",
        f"Tool calls served by backend {backend!r}",
    ).inc()


def record_backend_request(backend: str, *, success: bool) -> None:
    """Increment backend request counters split by outcome.

    Args:
        backend: Backend name (e.g. ``"github"``).
        success: ``True`` if the request succeeded, ``False`` otherwise.
    """
    label = "success" if success else "failure"
    _REGISTRY.counter(
        f"gateway.backend.{backend}.requests.{label}",
        f"Backend requests for {backend!r} that completed with status {label!r}",
    ).inc()
