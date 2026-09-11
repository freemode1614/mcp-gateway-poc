"""Tests for observability.metrics: counter, snapshot, Prometheus export."""

from __future__ import annotations

import pytest

from mcp_gateway.observability.metrics import (
    Counter,
    MetricsRegistry,
    get_metrics,
    record_backend_request,
    record_tool_call,
)


def _snapshot() -> dict[str, int]:
    """Return the singleton registry's counters as a plain dict."""
    return dict(get_metrics().snapshot())


def test_counter_inc_increments_by_default_amount() -> None:
    c = Counter("test.calls")
    assert c.value == 0
    c.inc()
    assert c.value == 1
    c.inc()
    assert c.value == 2


def test_counter_inc_accepts_custom_amount() -> None:
    c = Counter("test.calls")
    c.inc(5)
    assert c.value == 5
    c.inc(amount=3)
    assert c.value == 8


def test_counter_rejects_negative_amount() -> None:
    c = Counter("test.calls")
    with pytest.raises(ValueError, match="cannot be decremented"):
        c.inc(-1)


def test_counter_exposes_name_and_help() -> None:
    c = Counter("metric.foo", "Total foo events")
    assert c.name == "metric.foo"
    assert c.help == "Total foo events"


def test_registry_returns_same_counter_on_repeated_lookup() -> None:
    reg = MetricsRegistry()
    a = reg.counter("shared", "shared counter")
    b = reg.counter("shared")
    assert a is b
    a.inc()
    assert b.value == 1


def test_registry_snapshot_returns_current_values() -> None:
    reg = MetricsRegistry()
    reg.counter("alpha").inc(2)
    reg.counter("beta").inc(7)
    snap = reg.snapshot()
    assert snap == {"alpha": 2, "beta": 7}


def test_registry_render_prometheus_emits_valid_exposition() -> None:
    reg = MetricsRegistry()
    reg.counter("gateway.test", "A test counter").inc(3)
    out = reg.render_prometheus()
    assert "# HELP gateway.test A test counter" in out
    assert "# TYPE gateway.test counter" in out
    assert "gateway.test 3" in out


def test_record_tool_call_increments_global_and_per_backend() -> None:
    record_tool_call("demo_one", "demo_one.echo")
    snap = _snapshot()
    assert snap["gateway.tool_calls.total"] >= 1
    assert snap["gateway.backend.demo_one.tool_calls"] >= 1


def test_record_backend_request_splits_success_and_failure() -> None:
    record_backend_request("demo_two", success=True)
    record_backend_request("demo_two", success=True)
    record_backend_request("demo_two", success=False)
    snap = _snapshot()
    assert snap["gateway.backend.demo_two.requests.success"] >= 2
    assert snap["gateway.backend.demo_two.requests.failure"] >= 1
