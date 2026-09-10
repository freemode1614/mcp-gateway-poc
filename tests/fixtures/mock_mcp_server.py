"""A minimal MCP server used by E2E tests using the low-level Server API."""

from __future__ import annotations

import asyncio
import sys

from mcp.server import Server
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server
from mcp.types import (
    CallToolRequestParams,
    CallToolResult,
    ListResourcesRequest,
    ListResourcesResult,
    ListToolsRequest,
    ListToolsResult,
    ReadResourceRequestParams,
    ReadResourceResult,
    Resource,
    ServerCapabilities,
    TextContent,
    TextResourceContents,
    Tool,
)


server: Server = Server("mock_backend")


ECHO_TOOL = Tool(
    name="echo",
    description="Echoes its argument back",
    inputSchema={
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
    },
)
ADD_TOOL = Tool(
    name="add",
    description="Adds two numbers",
    inputSchema={
        "type": "object",
        "properties": {
            "a": {"type": "number"},
            "b": {"type": "number"},
        },
        "required": ["a", "b"],
    },
)
HELLO_RESOURCE = Resource(
    uri="mock://hello",
    name="hello",
    description="A greeting",
    mimeType="text/plain",
)


async def _list_tools(_ctx, _params) -> ListToolsResult:
    return ListToolsResult(tools=[ECHO_TOOL, ADD_TOOL])


async def _call_tool(_ctx, params: CallToolRequestParams) -> CallToolResult:
    name = params.name
    arguments = params.arguments or {}
    if name == "echo":
        return CallToolResult(
            content=[TextContent(type="text", text=str(arguments.get("text", "")))],
            isError=False,
        )
    if name == "add":
        return CallToolResult(
            content=[
                TextContent(
                    type="text",
                    text=str(float(arguments["a"]) + float(arguments["b"])),
                )
            ],
            isError=False,
        )
    raise ValueError(f"unknown tool: {name}")


async def _list_resources(_ctx, _params) -> ListResourcesResult:
    return ListResourcesResult(resources=[HELLO_RESOURCE])


async def _read_resource(_ctx, params: ReadResourceRequestParams) -> ReadResourceResult:
    uri = str(params.uri)
    if uri == "mock://hello":
        return ReadResourceResult(
            contents=[
                TextResourceContents(
                    uri=uri, mimeType="text/plain", text="hello world"
                )
            ]
        )
    raise ValueError(f"unknown resource: {uri}")


server.add_request_handler("tools/list", ListToolsRequest, _list_tools)
server.add_request_handler("tools/call", CallToolRequestParams, _call_tool)
server.add_request_handler("resources/list", ListResourcesRequest, _list_resources)
server.add_request_handler("resources/read", ReadResourceRequestParams, _read_resource)


async def main() -> None:
    caps = ServerCapabilities(
        tools={"listChanged": False},
        resources={"listChanged": False},
    )
    init = InitializationOptions(
        server_name="mock_backend",
        server_version="0.1.0",
        capabilities=caps,
    )
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, init)


if __name__ == "__main__":
    asyncio.run(main())
    sys.exit(0)
