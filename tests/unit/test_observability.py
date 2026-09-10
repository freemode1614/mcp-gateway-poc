"""Tests for observability: structured JSON logging output."""

from __future__ import annotations

import io
import json

import structlog

from mcp_gateway.observability import (
    configure_logging,
    get_logger,
    get_request_id,
    set_request_id,
)


def test_configure_logging_emits_json_to_stdout(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("info")
    log = get_logger("test.module")
    log.info("hello", foo="bar")
    captured = capsys.readouterr().out
    lines = [line for line in captured.splitlines() if line.strip()]
    assert lines, "expected at least one log line"
    record = json.loads(lines[-1])
    assert record["event"] == "hello"
    assert record["foo"] == "bar"
    assert record["level"] == "info"
    assert "timestamp" in record


def test_request_id_propagates_to_log(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("info")
    log = get_logger("test.module")
    set_request_id("req_abc12345")
    try:
        log.info("with_rid")
    finally:
        set_request_id(None)
    captured = capsys.readouterr().out
    last_line = [line for line in captured.splitlines() if "with_rid" in line][-1]
    record = json.loads(last_line)
    assert record["request_id"] == "req_abc12345"


def test_get_request_id_returns_current_value() -> None:
    set_request_id("req_xyz00000")
    try:
        assert get_request_id() == "req_xyz00000"
    finally:
        set_request_id(None)
    assert get_request_id() is None


def test_log_levels_filtered(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("warning")
    log = get_logger("test.module")
    log.info("should_be_filtered")
    log.warning("should_appear")
    captured = capsys.readouterr().out
    assert "should_be_filtered" not in captured
    assert "should_appear" in captured
