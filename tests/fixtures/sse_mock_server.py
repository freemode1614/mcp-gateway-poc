"""Mock MCP server that exposes itself over SSE for E2E testing the HttpSseBackend."""

from __future__ import annotations

import asyncio
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
    app = server.sse_app()
    config = uvicorn.Config(
        app=app, host="127.0.0.1", port=int(sys.argv[1]), log_level="warning"
    )
    uvicorn.Server(config).run()


if __name__ == "__main__":
    run()
