"""HTTP/SSE frontend: FastAPI app, middleware, MCP transport, /health."""

from __future__ import annotations

from .app import build_app

__all__ = ["build_app"]
