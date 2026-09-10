"""Core: Registry (catalog), Router (dispatch), BackendConnectionManager (lifecycle)."""

from __future__ import annotations

from .manager import BackendConnectionManager, RestartPolicy
from .registry import CatalogEntry, Registry
from .router import Router

__all__ = [
    "BackendConnectionManager",
    "CatalogEntry",
    "Registry",
    "RestartPolicy",
    "Router",
]
