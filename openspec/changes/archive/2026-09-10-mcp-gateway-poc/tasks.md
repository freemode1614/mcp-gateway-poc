## 1. Project scaffolding

- [x] 1.1 Add runtime + dev dependencies to `pyproject.toml` (`fastapi`, `uvicorn[standard]`, `httpx`, `mcp`, `pyyaml`, `pydantic`, `structlog`, `watchfiles`, `pytest`, `pytest-asyncio`, `pytest-cov`, `anyio`)
- [x] 1.2 Create package layout: `src/mcp_gateway/{frontend,backend,core,config,observability}` with empty `__init__.py` files and a `py.typed` marker
- [x] 1.3 Configure `pytest` (`asyncio_mode = auto`, testpaths, `src` layout) and `pytest-cov` (≥ 80% overall, ≥ 90% core)
- [x] 1.4 Add CLI entry point `mcp-gateway = "mcp_gateway.cli:main"` and an `argparse`-based CLI that accepts `--config` and `--host` / `--port` overrides

## 2. Configuration module

- [x] 2.1 Define Pydantic models: `GatewayConfig`, `BackendConfig` (discriminated union on `transport`), `StdioBackendConfig`, `SseBackendConfig`
- [x] 2.2 Implement `${env:VAR}` interpolation helper and unit tests for substitution + missing-var failure
- [x] 2.3 Implement `load_config(path: Path) -> GatewayConfig` with validation rules (name regex, port range, required fields, duplicate detection) and unit tests for each rejection path
- [x] 2.4 Implement `ConfigWatcher` wrapping `watchfiles` with 500 ms debounce and an `on_change` async callback

## 3. Backend connection layer

- [x] 3.1 Define `BackendConnection` Protocol (name, start, stop, healthcheck, initialize, list_tools, call_tool, list_resources, read_resource)
- [x] 3.2 Implement `StdioBackend` using `mcp` SDK `stdio_client` + `ClientSession`; pass env, honor `startup_timeout_s`, return graceful errors
- [x] 3.3 Implement `HttpSseBackend` using `mcp` SDK `sse_client` + `ClientSession`; forward headers, honor `startup_timeout_s`
- [x] 3.4 Implement exponential-backoff restart (1s/2s/4s, max 3 attempts) with `permanently_failed` terminal state
- [x] 3.5 Unit-test a `FakeBackendConnection` (no SDK import) for lifecycle and protocol surface; integration-test real stdio + SSE backends against an in-process MCP mock server

## 4. Core: Registry and Router

- [x] 4.1 Implement `CatalogEntry` dataclass and `Registry` with `asyncio.Lock`; methods `add_backend`, `remove_backend`, `lookup_tool`, `lookup_resource`, `list_tools`, `list_resources`
- [x] 4.2 Unit tests: prefix applied, duplicate `prefixed_name` prevented, backend removal atomic, unknown lookup returns `None`
- [x] 4.3 Implement `Router.dispatch_tool_call(name, args)` raising `UnknownToolError` and `BackendUnavailableError`; strips prefix before forwarding
- [x] 4.4 Implement `Router.dispatch_resource_read(uri)` using URI scheme as backend key; strips scheme before forwarding
- [x] 4.5 Unit tests for Router covering: successful dispatch, unknown tool, unknown URI, unhealthy backend, prefix-stripping correctness

## 5. Frontend: FastAPI app and middleware

- [x] 5.1 Implement `request_id` middleware: read `X-Request-ID` if valid else generate `req_<8-hex>`; bind into a `structlog` contextvar; return header on response
- [x] 5.2 Implement logging middleware: emit `event=tool_call` (and equivalents) with `request_id`, `backend`, `tool`, `duration_ms`, `status`
- [x] 5.3 Implement SSE endpoint `GET /sse` that opens the stream and emits the `endpoint` event per MCP spec
- [x] 5.4 Implement JSON-RPC dispatcher on `POST /messages`: parse JSON-RPC, route by method (`initialize`, `ping`, `tools/list`, `tools/call`, `resources/list`, `resources/read`), return JSON-RPC responses with error codes `-32601`, `-32603`, `-32001`
- [x] 5.5 Implement `GET /health` returning 200/503 with per-backend status map
- [x] 5.6 Wire everything in `app.py` (FastAPI factory) and `main()` (uvicorn launch)

## 6. BackendConnectionManager and hot reload

- [x] 6.1 Implement `BackendConnectionManager` holding a `{name: BackendConnection}` dict plus the `Registry`; methods `start_all`, `stop_all`, `get_session`, `reload(new_config)`
- [x] 6.2 Implement diff logic in `reload`: added → start+register; removed → stop+unregister; modified → stop+start; failed start does not roll back others
- [x] 6.3 Wire `ConfigWatcher.on_change` to manager reload with structured `reload_applied` log
- [x] 6.4 Integration test: write YAML to `tmp_path`, start gateway, edit file to add a backend, assert tools appear within debounce window; remove and assert cleanup

## 7. Observability

- [x] 7.1 Configure `structlog` with JSON renderer to stdout, ISO-8601 timestamps, level from `gateway.log_level`
- [x] 7.2 Emit lifecycle events (`startup`, `backend_connected`, `backend_disconnected`, `reload_applied`, `config_error`) with consistent fields
- [x] 7.3 Unit test: capture stdout, assert one JSON object per line with required fields per scenario

## 8. Acceptance checklist

- [x] 8.1 Start gateway with example YAML; `tools/list` returns both backends' tools with `<backend>.` prefix
- [x] 8.2 At least one stdio and one HTTP/SSE backend run end-to-end
- [x] 8.3 `tools/call` routes correctly with prefix stripped; `resources/read` routes by URI scheme
- [x] 8.4 Edit YAML → within 5 s new backend's tools appear, removed backend's tools disappear
- [x] 8.5 Killing one backend's process does not affect others; logs show `backend_disconnected` and recovery or `permanently_failed`
- [x] 8.6 `curl /health` returns per-backend statuses and correct HTTP code
- [x] 8.7 Every tool/resource log line carries `request_id`, `backend`, `duration_ms`, `status`
- [x] 8.8 `pytest --cov` reports ≥ 80% overall, ≥ 90% on `src/mcp_gateway/core/` and `src/mcp_gateway/config/`
- [x] 8.9 Ship `examples/mcp-gateway.yaml` and `examples/mock_backend.py` so a fresh checkout can run the gateway in two commands
