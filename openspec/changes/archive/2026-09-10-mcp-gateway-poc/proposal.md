## Why

Developers using MCP clients (Claude Desktop, IDE plugins, custom agents) frequently need access to multiple MCP backend servers, but most clients only connect to one endpoint. A local **MCP Gateway** that aggregates multiple backends behind a single URL solves this: one client connection, all tools/resources visible, with a unified namespace and a single observability surface. The PoC also acts as a **transport adapter** — bridging stdio subprocesses and HTTP/SSE backends behind one HTTP/SSE frontend — which is the most-requested local MCP infrastructure pattern.

## What Changes

- New Python 3.13 service `mcp-gateway` that listens on `127.0.0.1:<port>` and exposes an MCP-over-SSE / Streamable HTTP endpoint.
- Plugin model for backends: each backend is declared in YAML with a transport type (`stdio` or `sse`); gateway spawns/manages them and reuses the official `mcp` SDK client to talk MCP.
- Tool and resource names from each backend are **prefixed** with `<backend_name>.` before being merged into a unified catalog returned by `tools/list` and `resources/list`.
- `tools/call` and `resources/read` requests are routed to the matching backend by parsing the prefix; the prefix is stripped before forwarding.
- YAML configuration with `${env:VAR}` interpolation, schema validation, and file-watcher-based hot reload (add/remove/restart diffed).
- Structured JSON logging with `request_id` propagation across HTTP, router, and backend layers; `GET /health` endpoint reports per-backend status.
- One backend failing or crashing does not affect the others.

## Capabilities

### New Capabilities

- `mcp-frontend`: HTTP/SSE server that speaks MCP wire protocol to clients, dispatches JSON-RPC requests to the router, and streams SSE events back.
- `backend-connection`: Stdio and HTTP/SSE backend adapters built on the official `mcp` SDK `ClientSession`, with start/stop/healthcheck lifecycle and exponential-backoff reconnect on backend crash.
- `registry-routing`: Unified in-memory catalog aggregating tools/resources from all backends (prefixed with `<backend_name>.`), and a router that resolves prefixed names to the owning backend for `tools/call` and `resources/read`.
- `configuration`: YAML config schema, `${env:VAR}` interpolation, startup-time validation, and file-watcher hot reload with debounced diff apply.
- `observability`: Structured JSON logging with `request_id` middleware, request duration tracking, and `GET /health` reporting per-backend status.

### Modified Capabilities

None — this is a greenfield project with no existing capabilities.

## Impact

- **New files / modules** under `src/mcp_gateway/`:
  - `frontend/` — FastAPI app, SSE endpoint, middleware
  - `backend/` — `BackendConnection` protocol, `StdioBackend`, `HttpSseBackend`
  - `core/` — `Registry`, `Router`, `BackendConnectionManager`
  - `config/` — YAML loader, schema validator, file watcher
  - `observability/` — structlog setup, request_id middleware
- **New dependencies**: `fastapi`, `uvicorn[standard]`, `httpx`, `mcp` (official SDK), `pyyaml`, `pydantic`, `structlog`, `watchfiles`, `pytest`, `pytest-asyncio`, `pytest-cov`.
- **External systems**: relies on backend MCP servers implementing the MCP spec (`initialize`, `tools/list`, `tools/call`, `resources/list`, `resources/read`).
- **Out of scope**: authentication/authorization (gateway binds `127.0.0.1`), prompts/sampling/elicitation/roots primitives, multi-tenant quota, persistent state.
