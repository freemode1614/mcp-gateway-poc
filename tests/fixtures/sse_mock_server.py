"""Mock MCP server that exposes itself over HTTP/streamable-SSE for E2E testing the HttpSseBackend.

The new `mcp` SDK (1.2+) recommends the streamable HTTP transport on `/mcp`.
The legacy SSE transport is still available via `sse_app()` but is incompatible
with the current client SDK, so we use `streamable_http_app()` here.
"""

from __future__ import annotations

import sys

import uvicorn
from mcp.server.mcpserver import MCPServer

server = MCPServer("sse_mock")


@server.tool(name="sse_echo", description="Echoes via SSE")
async def sse_echo(text: str) -> str:
    return text


@server.tool(name="sse_add", description="Adds via SSE")
async def sse_add(a: float, b: float) -> float:
    return a + b


@server.resource(uri="sse://greeting", name="greeting", description="A greeting")
async def greeting() -> str:
    return "greetings via SSE"


def run() -> None:
    app = server.streamable_http_app()
    config = uvicorn.Config(app=app, host="127.0.0.1", port=int(sys.argv[1]), log_level="warning")
    uvicorn.Server(config).run()


if __name__ == "__main__":
    run()
