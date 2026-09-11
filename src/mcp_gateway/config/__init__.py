"""Configuration loading, validation, and hot-reload watcher."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

from .watcher import ConfigWatcher

NAME_PATTERN = re.compile(r"^[a-z0-9_-]+$")


class GatewaySettings(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8765
    log_level: str = "info"

    @field_validator("host")
    @classmethod
    def _host_non_empty(cls, value: str) -> str:
        if not value:
            raise ValueError("gateway.host must not be empty")
        return value

    @field_validator("port")
    @classmethod
    def _port_in_range(cls, value: int) -> int:
        if not 1 <= value <= 65535:
            raise ValueError(f"gateway.port must be in [1, 65535], got {value}")
        return value

    @field_validator("log_level")
    @classmethod
    def _log_level_valid(cls, value: str) -> str:
        allowed = {"debug", "info", "warning", "error"}
        if value not in allowed:
            raise ValueError(f"gateway.log_level must be one of {sorted(allowed)}, got {value!r}")
        return value


class ReloadSettings(BaseModel):
    enabled: bool = True
    debounce_ms: int = 500

    @field_validator("debounce_ms")
    @classmethod
    def _debounce_positive(cls, value: int) -> int:
        if value < 0:
            raise ValueError("gateway.reload.debounce_ms must be >= 0")
        return value


class _GatewayBlock(GatewaySettings):
    reload: ReloadSettings = Field(default_factory=ReloadSettings)


class StdioBackendConfig(BaseModel):
    name: str
    transport: str = "stdio"
    command: str
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    startup_timeout_s: float = 30.0

    @field_validator("name")
    @classmethod
    def _name_format(cls, value: str) -> str:
        if not NAME_PATTERN.fullmatch(value):
            raise ValueError(f"invalid backend name {value!r}: must match {NAME_PATTERN.pattern}")
        return value

    @field_validator("startup_timeout_s")
    @classmethod
    def _timeout_positive(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("startup_timeout_s must be > 0")
        return value


class SseBackendConfig(BaseModel):
    name: str
    transport: str = "sse"
    url: str
    headers: dict[str, str] = Field(default_factory=dict)
    startup_timeout_s: float = 30.0

    @field_validator("name")
    @classmethod
    def _name_format(cls, value: str) -> str:
        if not NAME_PATTERN.fullmatch(value):
            raise ValueError(f"invalid backend name {value!r}: must match {NAME_PATTERN.pattern}")
        return value

    @field_validator("url")
    @classmethod
    def _url_required(cls, value: str) -> str:
        if not value:
            raise ValueError("sse backend requires non-empty url")
        return value

    @field_validator("startup_timeout_s")
    @classmethod
    def _timeout_positive(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("startup_timeout_s must be > 0")
        return value


BackendConfig = StdioBackendConfig | SseBackendConfig


class GatewayConfig(BaseModel):
    gateway: _GatewayBlock = Field(default_factory=_GatewayBlock)
    backends: list[BackendConfig] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_unique_backend_names(self) -> GatewayConfig:
        seen: set[str] = set()
        for backend in self.backends:
            if backend.name in seen:
                raise ValueError(f"duplicate backend name {backend.name!r}")
            seen.add(backend.name)
        return self


_ENV_PATTERN = re.compile(r"\$\{env:([A-Za-z_][A-Za-z0-9_]*)\}")


def interpolate_env(value: str, *, source: str, backend_name: str) -> str:
    """Replace ${env:VAR} placeholders in `value` using os.environ.

    Raises ValueError on missing variables, citing the variable and where it was referenced.
    """

    def replace(match: re.Match[str]) -> str:
        var_name = match.group(1)
        if var_name not in os.environ:
            raise ValueError(
                f"environment variable {var_name!r} referenced in {source} for backend "
                f"{backend_name!r} is not set"
            )
        return os.environ[var_name]

    return _ENV_PATTERN.sub(replace, value)


def _interpolate_backend(backend: BackendConfig) -> BackendConfig:
    if isinstance(backend, StdioBackendConfig):
        new_env = {
            key: interpolate_env(val, source=f"env.{key}", backend_name=backend.name)
            for key, val in backend.env.items()
        }
        new_command = interpolate_env(backend.command, source="command", backend_name=backend.name)
        new_args = [
            interpolate_env(arg, source=f"args[{i}]", backend_name=backend.name)
            for i, arg in enumerate(backend.args)
        ]
        return backend.model_copy(update={"env": new_env, "command": new_command, "args": new_args})
    new_headers = {
        key: interpolate_env(val, source=f"headers.{key}", backend_name=backend.name)
        for key, val in backend.headers.items()
    }
    new_url = interpolate_env(backend.url, source="url", backend_name=backend.name)
    return backend.model_copy(update={"headers": new_headers, "url": new_url})


def _coerce_backend(raw: dict[str, Any]) -> BackendConfig:
    transport = raw.get("transport", "stdio")
    if transport == "stdio":
        return StdioBackendConfig.model_validate(raw)
    if transport == "sse":
        return SseBackendConfig.model_validate(raw)
    raise ValueError(
        f"unknown transport {transport!r} for backend {raw.get('name')!r}; "
        "expected 'stdio' or 'sse'"
    )


def load_config(path: Path) -> GatewayConfig:
    """Load, interpolate, and validate a YAML config file."""
    if not path.is_file():
        raise FileNotFoundError(f"config file not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"config root must be a mapping, got {type(raw).__name__}")
    gateway_block = raw.get("gateway", {}) or {}
    backends_raw = raw.get("backends", []) or []
    if not isinstance(backends_raw, list):
        raise ValueError("config.backends must be a list")
    try:
        backends = [_coerce_backend(b) for b in backends_raw]
        config = GatewayConfig.model_validate({"gateway": gateway_block, "backends": backends})
    except ValidationError as exc:
        raise ValueError(f"invalid config: {exc}") from exc
    interpolated = [_interpolate_backend(b) for b in config.backends]
    return config.model_copy(update={"backends": interpolated})


__all__ = [
    "BackendConfig",
    "ConfigWatcher",
    "GatewayConfig",
    "GatewaySettings",
    "NAME_PATTERN",
    "ReloadSettings",
    "SseBackendConfig",
    "StdioBackendConfig",
    "interpolate_env",
    "load_config",
]
