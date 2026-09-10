"""FastAPI application factory and JSON-RPC dispatcher."""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from mcp import types as mcp_types
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from ..backend import BackendState, BackendUnavailableError, ToolCallError, UnknownToolError
from ..core import BackendConnectionManager, Router
from ..observability import get_logger
from .middleware import RequestIDMiddleware

logger = get_logger(__name__)

GATEWAY_SERVER_INFO = {
    "name": "mcp-gateway",
    "version": "0.1.0",
}


class JsonRpcRequest(BaseModel):
    jsonrpc: str = "2.0"
    id: Any | None = None
    method: str
    params: dict[str, Any] | None = None


class JsonRpcError(BaseModel):
    code: int
    message: str
    data: Any | None = None


ERROR_METHOD_NOT_FOUND = -32601
ERROR_INTERNAL = -32603
ERROR_BACKEND_UNAVAILABLE = -32001
ERROR_TOOL_CALL_FAILED = -32002
ERROR_INVALID_REQUEST = -32600


def build_app(*, manager: BackendConnectionManager) -> FastAPI:
    router = Router(manager.registry, manager.get_backend)
    app = FastAPI(title="mcp-gateway")
    app.add_middleware(RequestIDMiddleware)
    app.state.manager = manager
    app.state.router = router

    @app.get("/sse")
    async def sse_endpoint(request: Request) -> Response:
        async def event_generator():
            messages_url = str(request.url_for("messages_endpoint"))
            yield {
                "event": "endpoint",
                "data": json.dumps({"uri": messages_url}),
            }
            try:
                while True:
                    await asyncio.sleep(15.0)
                    yield {"event": "ping", "data": "{}"}
            except asyncio.CancelledError:
                return

        return EventSourceResponse(event_generator())

    @app.post("/messages", name="messages_endpoint")
    async def messages_endpoint(
        request: Request, payload: JsonRpcRequest
    ) -> Response:
        return await _dispatch(request, payload, router, manager)

    @app.get("/health")
    async def health() -> JSONResponse:
        statuses: dict[str, str] = {}
        any_healthy = False
        for backend in manager.list_backends():
            state = backend.state.value
            statuses[backend.name] = state
            if state == BackendState.HEALTHY.value:
                any_healthy = True
        if not statuses:
            return JSONResponse({"status": "down", "backends": {}}, status_code=503)
        if any_healthy and all(s == BackendState.HEALTHY.value for s in statuses.values()):
            return JSONResponse({"status": "ok", "backends": statuses})
        if any_healthy:
            return JSONResponse({"status": "degraded", "backends": statuses})
        return JSONResponse(
            {"status": "down", "backends": statuses}, status_code=503
        )

    return app


async def _dispatch(
    request: Request,
    payload: JsonRpcRequest,
    router: Router,
    manager: BackendConnectionManager,
) -> Response:
    if payload.jsonrpc != "2.0":
        return _error_response(payload.id, ERROR_INVALID_REQUEST, "jsonrpc must be '2.0'")
    method = payload.method
    params = payload.params or {}
    started = time.perf_counter()

    try:
        if method == "initialize":
            result = _build_initialize_result(manager)
        elif method == "ping":
            result = {}
        elif method == "tools/list":
            result = await _list_tools(manager)
        elif method == "tools/call":
            result = await _call_tool(router, params)
        elif method == "resources/list":
            result = await _list_resources(manager)
        elif method == "resources/read":
            result = await _read_resource(router, params)
        else:
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            logger.info(
                "rpc_error",
                method=method,
                duration_ms=duration_ms,
                status="error",
                code=ERROR_METHOD_NOT_FOUND,
            )
            return _error_response(
                payload.id, ERROR_METHOD_NOT_FOUND, f"method not found: {method}"
            )
    except UnknownToolError as exc:
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        logger.info(
            "rpc_error",
            method=method,
            duration_ms=duration_ms,
            status="error",
            code=ERROR_METHOD_NOT_FOUND,
            error=str(exc),
        )
        return _error_response(payload.id, ERROR_METHOD_NOT_FOUND, str(exc))
    except BackendUnavailableError as exc:
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        logger.info(
            "rpc_error",
            method=method,
            backend=exc.backend_name,
            duration_ms=duration_ms,
            status="error",
            code=ERROR_BACKEND_UNAVAILABLE,
            error=str(exc),
        )
        return _error_response(payload.id, ERROR_BACKEND_UNAVAILABLE, str(exc))
    except ToolCallError as exc:
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        logger.info(
            "tool_call_error",
            method=method,
            backend=exc.backend,
            tool=exc.tool,
            duration_ms=duration_ms,
            status="error",
            error=exc.message,
        )
        return _error_response(payload.id, ERROR_TOOL_CALL_FAILED, str(exc))
    except Exception as exc:  # noqa: BLE001
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        logger.exception(
            "internal_error",
            method=method,
            duration_ms=duration_ms,
            status="error",
        )
        return _error_response(
            payload.id, ERROR_INTERNAL, f"internal error: {exc}"
        )

    duration_ms = round((time.perf_counter() - started) * 1000, 2)
    if method == "tools/call":
        tool_name = params.get("name", "")
        backend = tool_name.split(".", 1)[0] if "." in tool_name else ""
        logger.info(
            "tool_call",
            method=method,
            backend=backend,
            tool=tool_name,
            duration_ms=duration_ms,
            status="ok",
            args_size_bytes=len(json.dumps(params.get("arguments", {}))),
        )
    else:
        logger.info(
            "rpc_call",
            method=method,
            duration_ms=duration_ms,
            status="ok",
        )
    return JSONResponse(
        {"jsonrpc": "2.0", "id": payload.id, "result": result}
    )


def _build_initialize_result(manager: BackendConnectionManager) -> dict[str, Any]:
    has_tools = any(manager.registry.list_tools())
    has_resources = any(manager.registry.list_resources())
    capabilities: dict[str, Any] = {}
    if has_tools:
        capabilities["tools"] = {"listChanged": False}
    if has_resources:
        capabilities["resources"] = {"listChanged": False}
    return {
        "protocolVersion": "2024-11-05",
        "serverInfo": GATEWAY_SERVER_INFO,
        "capabilities": capabilities,
    }


async def _list_tools(manager: BackendConnectionManager) -> dict[str, Any]:
    entries = manager.registry.list_tools()
    tools: list[dict[str, Any]] = []
    for entry in entries:
        tool_name = entry.prefixed_name.split(".", 1)[1]
        tools.append(
            {
                "name": entry.prefixed_name,
                "description": f"[{entry.backend_name}] {tool_name}",
                "inputSchema": entry.schema or {"type": "object", "properties": {}},
            }
        )
    return {"tools": tools}


async def _call_tool(router: Router, params: dict[str, Any]) -> dict[str, Any]:
    name = params.get("name")
    if not isinstance(name, str):
        raise UnknownToolError(str(name))
    arguments = params.get("arguments") or {}
    if not isinstance(arguments, dict):
        arguments = {}
    result = await router.dispatch_tool_call(name, arguments)
    return _call_tool_result_to_json(result)


def _call_tool_result_to_json(result: mcp_types.CallToolResult) -> dict[str, Any]:
    content: list[dict[str, Any]] = []
    for item in result.content:
        if isinstance(item, mcp_types.TextContent):
            content.append({"type": "text", "text": item.text})
        elif isinstance(item, mcp_types.ImageContent):
            content.append(
                {
                    "type": "image",
                    "data": item.data,
                    "mimeType": item.mime_type,
                }
            )
        elif isinstance(item, mcp_types.AudioContent):
            content.append(
                {
                    "type": "audio",
                    "data": item.data,
                    "mimeType": item.mime_type,
                }
            )
        elif isinstance(item, mcp_types.EmbeddedResource):
            resource = item.resource
            content.append(
                {"type": "resource", "resource": _resource_to_json(resource)}
            )
        else:
            content.append({"type": "unknown", "raw": str(item)})
    return {"content": content, "isError": bool(result.is_error)}


async def _list_resources(manager: BackendConnectionManager) -> dict[str, Any]:
    entries = manager.registry.list_resources()
    resources = [
        {
            "uri": entry.prefixed_name,
            "name": entry.schema.get("name", entry.prefixed_name),
            "description": entry.schema.get("description", ""),
            "mimeType": entry.schema.get("mimeType") or None,
        }
        for entry in entries
    ]
    return {"resources": resources}


async def _read_resource(router: Router, params: dict[str, Any]) -> dict[str, Any]:
    uri = params.get("uri")
    if not isinstance(uri, str):
        raise UnknownToolError(str(uri))
    result = await router.dispatch_resource_read(uri)
    contents: list[dict[str, Any]] = []
    for item in result.contents:
        contents.append(_resource_contents_to_json(item))
    return {"contents": contents}


def _resource_contents_to_json(
    item: mcp_types.ResourceContents,
) -> dict[str, Any]:
    if isinstance(item, mcp_types.TextResourceContents):
        return {
            "uri": str(item.uri),
            "mimeType": getattr(item, "mime_type", None) or "text/plain",
            "text": item.text,
        }
    if isinstance(item, mcp_types.BlobResourceContents):
        return {
            "uri": str(item.uri),
            "mimeType": getattr(item, "mime_type", None) or "application/octet-stream",
            "blob": item.blob,
        }
    return {"uri": str(item.uri), "raw": str(item)}


def _resource_to_json(resource: Any) -> dict[str, Any]:
    if hasattr(resource, "model_dump"):
        return resource.model_dump(exclude_none=True)
    return {"uri": str(resource)}


def _error_response(request_id: Any, code: int, message: str) -> JSONResponse:
    return JSONResponse(
        {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": code, "message": message},
        }
    )


# Sentinel string for the unused-reference lint shim below.
BackendConnection_HEALTHY = "healthy"


__all__ = ["build_app"]
