"""In-memory catalog of tools and resources aggregated from all backends."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from mcp import types as mcp_types


@dataclass(frozen=True)
class CatalogEntry:
    prefixed_name: str
    backend_name: str
    real_name: str
    schema: dict[str, Any]

    @property
    def kind(self) -> str:
        return "tool" if "." in self.prefixed_name and "://" not in self.prefixed_name else "resource"


class Registry:
    """Aggregate tools/resources from all backends under a unified, prefixed view."""

    def __init__(self) -> None:
        self._tools: dict[str, CatalogEntry] = {}
        self._resources: dict[str, CatalogEntry] = {}
        self._lock = asyncio.Lock()

    async def add_backend_tools(
        self,
        backend_name: str,
        tools: list[mcp_types.Tool],
    ) -> None:
        async with self._lock:
            self._purge_backend_tools_locked(backend_name)
            for tool in tools:
                prefixed = _prefix(backend_name, tool.name)
                if prefixed in self._tools:
                    raise ValueError(
                        f"duplicate prefixed tool {prefixed!r} while adding backend "
                        f"{backend_name!r}"
                    )
                schema = (
                    tool.inputSchema
                    if isinstance(getattr(tool, "inputSchema", None), dict)
                    else tool.input_schema
                    if isinstance(getattr(tool, "input_schema", None), dict)
                    else {}
                )
                if not isinstance(schema, dict):
                    schema = {}
                self._tools[prefixed] = CatalogEntry(
                    prefixed_name=prefixed,
                    backend_name=backend_name,
                    real_name=tool.name,
                    schema=schema,
                )

    async def add_backend_resources(
        self,
        backend_name: str,
        resources: list[mcp_types.Resource],
    ) -> None:
        async with self._lock:
            self._purge_backend_resources_locked(backend_name)
            for resource in resources:
                prefixed = _prefix_resource_uri(backend_name, str(resource.uri))
                mime = getattr(resource, "mime_type", None) or getattr(
                    resource, "mimeType", None
                ) or ""
                self._resources[prefixed] = CatalogEntry(
                    prefixed_name=prefixed,
                    backend_name=backend_name,
                    real_name=str(resource.uri),
                    schema={
                        "name": resource.name,
                        "description": resource.description or "",
                        "mimeType": mime,
                    },
                )

    async def remove_backend(self, backend_name: str) -> None:
        async with self._lock:
            self._purge_backend_tools_locked(backend_name)
            self._purge_backend_resources_locked(backend_name)

    def lookup_tool(self, prefixed_name: str) -> CatalogEntry | None:
        return self._tools.get(prefixed_name)

    def lookup_resource(self, prefixed_uri: str) -> CatalogEntry | None:
        return self._resources.get(prefixed_uri)

    def list_tools(self) -> list[CatalogEntry]:
        return list(self._tools.values())

    def list_resources(self) -> list[CatalogEntry]:
        return list(self._resources.values())

    def _purge_backend_tools_locked(self, backend_name: str) -> None:
        prefix = f"{backend_name}."
        to_delete = [k for k in self._tools if k.startswith(prefix)]
        for k in to_delete:
            del self._tools[k]

    def _purge_backend_resources_locked(self, backend_name: str) -> None:
        prefix = f"{backend_name}://"
        to_delete = [k for k in self._resources if k.startswith(prefix)]
        for k in to_delete:
            del self._resources[k]


def _prefix(backend_name: str, real_name: str) -> str:
    return f"{backend_name}.{real_name}"


def _prefix_resource_uri(backend_name: str, real_uri: str) -> str:
    """Rewrite a backend's native URI into `<backend>://<rest>`.

    The original scheme of the backend URI is dropped; the backend name becomes the
    routing tag. The remainder (including the leading `//`) is preserved verbatim.
    """
    parsed = urlparse(real_uri)
    rest = parsed.netloc + parsed.path
    if parsed.query:
        rest = f"{rest}?{parsed.query}"
    if parsed.fragment:
        rest = f"{rest}#{parsed.fragment}"
    if not rest.startswith("/"):
        rest = "/" + rest
    return f"{backend_name}://{rest.lstrip('/')}"


def strip_resource_uri(prefixed_uri: str) -> tuple[str, str]:
    """Inverse of `_prefix_resource_uri`: return (backend_name, native_uri).

    The native URI is reconstructed by prepending the backend name as the URI scheme
    and leaving the remainder untouched. (The gateway is the only consumer; it
    rebuilds the URI from the registered entry's real_name rather than parsing the
    scheme, but this helper is kept for symmetric testing.)
    """
    if "://" not in prefixed_uri:
        raise ValueError(f"not a prefixed resource URI: {prefixed_uri!r}")
    backend, rest = prefixed_uri.split("://", 1)
    return backend, rest


__all__ = ["CatalogEntry", "Registry"]
