"""Tests for the CLI entry point and command-line overrides."""

from __future__ import annotations

from pathlib import Path

import pytest

from mcp_gateway.cli import _build_parser, _resolve_config_path


def test_parser_has_config_host_port() -> None:
    parser = _build_parser()
    args = parser.parse_args(["--config", "x.yaml"])
    assert args.config == Path("x.yaml")
    assert args.host is None
    assert args.port is None

    args = parser.parse_args(["--config", "x.yaml", "--host", "0.0.0.0", "--port", "9000"])
    assert args.host == "0.0.0.0"
    assert args.port == 9000


def test_resolve_config_path_finds_explicit(tmp_path: Path) -> None:
    p = tmp_path / "explicit.yaml"
    p.write_text("backends: []")
    assert _resolve_config_path(p) == p


def test_resolve_config_path_env_var(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    p = tmp_path / "env.yaml"
    p.write_text("backends: []")
    monkeypatch.setenv("MCP_GATEWAY_CONFIG", str(p))
    assert _resolve_config_path(None) == p


def test_resolve_config_path_searches_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("MCP_GATEWAY_CONFIG", raising=False)
    (tmp_path / "mcp-gateway.yaml").write_text("backends: []")
    assert _resolve_config_path(None).name == "mcp-gateway.yaml"


def test_resolve_config_path_raises_when_no_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("MCP_GATEWAY_CONFIG", raising=False)
    with pytest.raises(SystemExit):
        _resolve_config_path(None)
