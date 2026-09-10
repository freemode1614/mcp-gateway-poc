"""Tests for the in-memory Registry."""

from __future__ import annotations

import pytest
from mcp import types as mcp_types

from mcp_gateway.core import CatalogEntry, Registry


def _tool(name: str, schema: dict | None = None) -> mcp_types.Tool:
    return mcp_types.Tool(
        name=name,
        description="d",
        inputSchema=schema or {"type": "object", "properties": {}},
    )


def _resource(uri: str, name: str = "r") -> mcp_types.Resource:
    return mcp_types.Resource(
        uri=uri, name=name, description="d", mimeType="text/plain"
    )


async def test_prefix_applied_to_tool_names() -> None:
    r = Registry()
    await r.add_backend_tools("github", [_tool("create_issue"), _tool("list_repos")])
    names = sorted(e.prefixed_name for e in r.list_tools())
    assert names == ["github.create_issue", "github.list_repos"]


async def test_prefix_isolates_same_named_tools_across_backends() -> None:
    r = Registry()
    await r.add_backend_tools("github", [_tool("create_issue")])
    await r.add_backend_tools("jira", [_tool("create_issue")])
    names = sorted(e.prefixed_name for e in r.list_tools())
    assert names == ["github.create_issue", "jira.create_issue"]
    assert r.lookup_tool("github.create_issue").real_name == "create_issue"


async def test_backend_removal_is_atomic() -> None:
    r = Registry()
    await r.add_backend_tools("github", [_tool("create_issue"), _tool("list_repos")])
    await r.add_backend_resources(
        "github", [_resource("file:///readme"), _resource("file:///changelog")]
    )
    await r.remove_backend("github")
    assert r.list_tools() == []
    assert r.list_resources() == []


async def test_unknown_lookup_returns_none() -> None:
    r = Registry()
    assert r.lookup_tool("nope.tool") is None
    assert r.lookup_resource("nope://x") is None


async def test_replace_tools_for_existing_backend() -> None:
    r = Registry()
    await r.add_backend_tools("github", [_tool("create_issue"), _tool("list_repos")])
    await r.add_backend_tools("github", [_tool("merge_pr")])
    names = sorted(e.prefixed_name for e in r.list_tools())
    assert names == ["github.merge_pr"]


async def test_resource_uri_prefixing_uses_backend_name_as_scheme() -> None:
    r = Registry()
    await r.add_backend_resources("github", [_resource("repo://foo/readme")])
    entries = r.list_resources()
    assert len(entries) == 1
    entry = entries[0]
    assert entry.prefixed_name.startswith("github://")
    assert "readme" in entry.prefixed_name


async def test_resource_uri_lookup_roundtrip() -> None:
    r = Registry()
    await r.add_backend_resources("github", [_resource("repo://foo/readme")])
    entry = r.list_resources()[0]
    found = r.lookup_resource(entry.prefixed_name)
    assert found is not None
    assert found.real_name == "repo://foo/readme"


async def test_catalog_entry_frozen() -> None:
    e = CatalogEntry(
        prefixed_name="x.y", backend_name="x", real_name="y", schema={}
    )
    with pytest.raises((AttributeError, Exception)):
        e.real_name = "z"  # type: ignore[misc]


async def test_duplicate_prefixed_name_impossible_after_purge() -> None:
    """Defensive: the purge-before-insert makes duplicate prefixed names impossible.

    This test documents the invariant: after the purge, adding a tool for a
    backend can never collide with another backend's prefixed name (because the
    prefix is part of the key).
    """
    r = Registry()
    await r.add_backend_tools("github", [_tool("dup")])
    await r.add_backend_tools("jira", [_tool("dup")])
    assert r.lookup_tool("github.dup") is not None
    assert r.lookup_tool("jira.dup") is not None


def test_catalog_entry_kind_property() -> None:
    e1 = CatalogEntry(prefixed_name="x.y", backend_name="x", real_name="y", schema={})
    assert e1.kind == "tool"
    e2 = CatalogEntry(
        prefixed_name="x://y", backend_name="x", real_name="y", schema={}
    )
    assert e2.kind == "resource"


def test_prefix_resource_uri_with_query_and_fragment() -> None:
    from mcp_gateway.core.registry import _prefix_resource_uri

    prefixed = _prefix_resource_uri("github", "https://example.com/path?q=1#frag")
    assert prefixed.startswith("github://")
    assert "q=1" in prefixed
    assert "frag" in prefixed


def test_strip_resource_uri_requires_scheme() -> None:
    from mcp_gateway.core.registry import strip_resource_uri

    with pytest.raises(ValueError, match="not a prefixed"):
        strip_resource_uri("no-scheme")
    backend, rest = strip_resource_uri("github://foo/bar")
    assert backend == "github"
    assert rest == "foo/bar"


def test_prefix_function() -> None:
    from mcp_gateway.core.registry import _prefix

    assert _prefix("x", "y") == "x.y"
