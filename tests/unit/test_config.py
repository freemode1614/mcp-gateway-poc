"""Tests for configuration loading, validation, and env interpolation."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from mcp_gateway.config import (
    NAME_PATTERN,
    GatewayConfig,
    SseBackendConfig,
    StdioBackendConfig,
    interpolate_env,
    load_config,
)


def _write(path: Path, body: str) -> Path:
    path.write_text(textwrap.dedent(body).lstrip("\n"))
    return path


def test_load_minimal_config(tmp_path: Path) -> None:
    cfg_path = _write(
        tmp_path / "c.yaml",
        """
        backends:
          - name: github
            transport: stdio
            command: uvx
            args: [mcp-server-github]
        """,
    )
    config = load_config(cfg_path)
    assert isinstance(config, GatewayConfig)
    assert len(config.backends) == 1
    backend = config.backends[0]
    assert isinstance(backend, StdioBackendConfig)
    assert backend.name == "github"
    assert backend.command == "uvx"
    assert backend.args == ["mcp-server-github"]


def test_invalid_backend_name_rejected(tmp_path: Path) -> None:
    cfg_path = _write(
        tmp_path / "c.yaml",
        """
        backends:
          - name: "Bad Name"
            transport: stdio
            command: echo
        """,
    )
    with pytest.raises(ValueError, match="invalid backend name"):
        load_config(cfg_path)


def test_duplicate_backend_name_rejected(tmp_path: Path) -> None:
    cfg_path = _write(
        tmp_path / "c.yaml",
        """
        backends:
          - name: github
            transport: stdio
            command: a
          - name: github
            transport: stdio
            command: b
        """,
    )
    with pytest.raises(ValueError, match="duplicate backend name"):
        load_config(cfg_path)


def test_stdio_missing_command_rejected(tmp_path: Path) -> None:
    cfg_path = _write(
        tmp_path / "c.yaml",
        """
        backends:
          - name: x
            transport: stdio
        """,
    )
    with pytest.raises(ValueError):
        load_config(cfg_path)


def test_sse_missing_url_rejected(tmp_path: Path) -> None:
    cfg_path = _write(
        tmp_path / "c.yaml",
        """
        backends:
          - name: x
            transport: sse
        """,
    )
    with pytest.raises(ValueError):
        load_config(cfg_path)


def test_invalid_port_rejected(tmp_path: Path) -> None:
    cfg_path = _write(
        tmp_path / "c.yaml",
        """
        gateway:
          port: 70000
        backends:
          - name: x
            transport: stdio
            command: echo
        """,
    )
    with pytest.raises(ValueError, match="port"):
        load_config(cfg_path)


def test_empty_host_rejected(tmp_path: Path) -> None:
    cfg_path = _write(
        tmp_path / "c.yaml",
        """
        gateway:
          host: ""
        backends:
          - name: x
            transport: stdio
            command: echo
        """,
    )
    with pytest.raises(ValueError, match="host"):
        load_config(cfg_path)


def test_invalid_log_level_rejected(tmp_path: Path) -> None:
    cfg_path = _write(
        tmp_path / "c.yaml",
        """
        gateway:
          log_level: trace
        backends:
          - name: x
            transport: stdio
            command: echo
        """,
    )
    with pytest.raises(ValueError, match="log_level"):
        load_config(cfg_path)


def test_negative_debounce_rejected(tmp_path: Path) -> None:
    cfg_path = _write(
        tmp_path / "c.yaml",
        """
        gateway:
          reload:
            debounce_ms: -1
        backends:
          - name: x
            transport: stdio
            command: echo
        """,
    )
    with pytest.raises(ValueError, match="debounce"):
        load_config(cfg_path)


def test_negative_startup_timeout_rejected(tmp_path: Path) -> None:
    cfg_path = _write(
        tmp_path / "c.yaml",
        """
        backends:
          - name: x
            transport: stdio
            command: echo
            startup_timeout_s: 0
        """,
    )
    with pytest.raises(ValueError, match="startup_timeout"):
        load_config(cfg_path)


def test_sse_name_format_rejected(tmp_path: Path) -> None:
    cfg_path = _write(
        tmp_path / "c.yaml",
        """
        backends:
          - name: "Bad Name"
            transport: sse
            url: http://127.0.0.1:9001/sse
        """,
    )
    with pytest.raises(ValueError, match="invalid backend name"):
        load_config(cfg_path)


def test_sse_empty_url_rejected(tmp_path: Path) -> None:
    cfg_path = _write(
        tmp_path / "c.yaml",
        """
        backends:
          - name: x
            transport: sse
            url: ""
        """,
    )
    with pytest.raises(ValueError, match="non-empty url"):
        load_config(cfg_path)


def test_root_must_be_mapping(tmp_path: Path) -> None:
    cfg_path = _write(tmp_path / "c.yaml", "- just\n- a\n- list\n")
    with pytest.raises(ValueError, match="mapping"):
        load_config(cfg_path)


def test_backends_must_be_list(tmp_path: Path) -> None:
    cfg_path = _write(
        tmp_path / "c.yaml",
        """
        backends:
          github: not a list
        """,
    )
    with pytest.raises(ValueError, match="must be a list"):
        load_config(cfg_path)


def test_backends_command_interpolation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MY_CMD", "/usr/bin/cmd")
    cfg_path = _write(
        tmp_path / "c.yaml",
        """
        backends:
          - name: x
            transport: stdio
            command: "${env:MY_CMD}"
            args: ["${env:MY_CMD}", "--flag"]
        """,
    )
    config = load_config(cfg_path)
    backend = config.backends[0]
    assert backend.command == "/usr/bin/cmd"
    assert backend.args == ["/usr/bin/cmd", "--flag"]


def test_sse_url_interpolation(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("REMOTE_URL", "http://x:1/sse")
    cfg_path = _write(
        tmp_path / "c.yaml",
        """
        backends:
          - name: x
            transport: sse
            url: "${env:REMOTE_URL}"
        """,
    )
    config = load_config(cfg_path)
    backend = config.backends[0]
    assert backend.url == "http://x:1/sse"


def test_unknown_transport_rejected(tmp_path: Path) -> None:
    cfg_path = _write(
        tmp_path / "c.yaml",
        """
        backends:
          - name: x
            transport: websocket
            command: echo
        """,
    )
    with pytest.raises(ValueError, match="unknown transport"):
        load_config(cfg_path)


def test_env_interpolation_substitutes_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MY_TOKEN", "abc123")
    assert interpolate_env("${env:MY_TOKEN}", source="env.T", backend_name="x") == "abc123"


def test_env_interpolation_missing_var_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEFINITELY_NOT_SET", raising=False)
    with pytest.raises(ValueError, match="DEFINITELY_NOT_SET"):
        interpolate_env("${env:DEFINITELY_NOT_SET}", source="env.T", backend_name="x")


def test_env_interpolation_in_yaml(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("GH_TOKEN", "secret")
    cfg_path = _write(
        tmp_path / "c.yaml",
        """
        backends:
          - name: github
            transport: stdio
            command: uvx
            args: [mcp-server-github]
            env:
              GITHUB_TOKEN: "${env:GH_TOKEN}"
        """,
    )
    config = load_config(cfg_path)
    backend = config.backends[0]
    assert isinstance(backend, StdioBackendConfig)
    assert backend.env == {"GITHUB_TOKEN": "secret"}


def test_env_interpolation_in_headers(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("API_KEY", "k")
    cfg_path = _write(
        tmp_path / "c.yaml",
        """
        backends:
          - name: jira
            transport: sse
            url: http://127.0.0.1:9001/sse
            headers:
              Authorization: "Bearer ${env:API_KEY}"
        """,
    )
    config = load_config(cfg_path)
    backend = config.backends[0]
    assert isinstance(backend, SseBackendConfig)
    assert backend.headers == {"Authorization": "Bearer k"}


def test_env_interpolation_missing_var_in_yaml_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("MISSING", raising=False)
    cfg_path = _write(
        tmp_path / "c.yaml",
        """
        backends:
          - name: jira
            transport: sse
            url: http://127.0.0.1:9001/sse
            headers:
              Authorization: "Bearer ${env:MISSING}"
        """,
    )
    with pytest.raises(ValueError, match="MISSING"):
        load_config(cfg_path)


def test_load_config_file_not_found(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "nonexistent.yaml")


def test_name_pattern_compiles() -> None:
    assert NAME_PATTERN.fullmatch("github")
    assert NAME_PATTERN.fullmatch("foo-bar_baz")
    assert NAME_PATTERN.fullmatch("a1")
    assert not NAME_PATTERN.fullmatch("Bad Name")
    assert not NAME_PATTERN.fullmatch("foo.bar")
