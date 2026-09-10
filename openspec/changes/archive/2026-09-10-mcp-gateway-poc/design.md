## Context

The project is greenfield: a Python 3.13 `pyproject.toml` with no dependencies and a one-line `main.py`. The goal is a local MCP Gateway PoC that aggregates multiple MCP backend servers behind a single HTTP/SSE endpoint exposed on `127.0.0.1`. Two primary use cases drive the design:

1. **Local aggregation** — one client connection sees the union of tools/resources from many backends.
2. **Transport adapter** — stdio subprocesses and remote HTTP/SSE servers both reachable through the same frontend transport.

The PoC must remain simple enough to implement and review in one cycle, while keeping clean seams so that production features (auth, multi-tenant, rate limiting, persistent state) can be added later without rewriting the core.

## Goals / Non-Goals

**Goals:**

- One YAML file describes all backends; the gateway starts them, talks MCP to them, and exposes them as one catalog.
- `<backend>.<tool>` and `<backend>://<resource>` naming isolates backends predictably.
- Hot reload of the YAML adds/removes/restarts backends without dropping other backends.
- All requests are logged in structured JSON with a `request_id`; `/health` exposes per-backend status.
- Core code paths covered by automated tests with a clear acceptance checklist.

**Non-Goals:**

- Authentication or authorization (the gateway binds `127.0.0.1`).
- MCP primitives beyond `tools` and `resources` (no prompts, sampling, elicitation, roots).
- Persistent state on disk — config is the only source of truth.
- Multi-tenant quotas, billing, audit trails, web admin UI.
- Production hardening: TLS, systemd integration, packaging beyond a runnable Python package.

## Decisions

### Decision: Hybrid architecture — FastAPI frontend + MCP SDK backend clients

The gateway is split into two halves:

- **Frontend** (FastAPI + uvicorn) owns the HTTP/SSE/Streamable HTTP transport to clients. Chosen because FastAPI/Starlette has first-class SSE support, easy middleware composition for `request_id`/logging, and is the de facto Python async web framework.
- **Backend** layer uses the official `mcp` Python SDK's `ClientSession` with `stdio_client` / `sse_client` transports. Chosen because the MCP wire protocol has many small details (capabilities negotiation, notifications, content blocks, error envelopes) that the SDK already implements and keeps current.

The two halves communicate through the **Registry** and **Router**, which are transport-agnostic — they only see prefixed names and dict arguments.

Alternatives considered:
- **Pure SDK (FastMCP server front and back)**: less code, but custom middleware (request_id, logging, namespace) would require monkey-patching the SDK's internals.
- **Hand-rolled JSON-RPC over FastAPI**: maximum control, but the PoC would spend most of its budget re-implementing MCP wire details instead of demonstrating gateway value.

### Decision: Registry holds an in-memory dict indexed by prefixed name

`Registry` is a single async-safe dict of `<prefixed_name> → CatalogEntry(backend_name, real_name, schema)`. Simple, fast, no external store. Locking is provided by `asyncio.Lock` (PoC is single-event-loop). A future migration to a richer store (SQLite for catalogs) is gated behind this interface.

### Decision: Router is a thin dispatcher with no schema validation or retry

Router only does: parse prefix → look up backend → call backend's `call_tool` / `read_resource` → translate errors to JSON-RPC codes. It deliberately does **not** validate arguments against the backend's input schema (that's the backend's job), does **not** retry (PoC scope), and does **not** transform results. Keeping it thin makes it trivially testable.

### Decision: Hot reload via `watchfiles` with debounce + diff apply

`watchfiles` notifies on file change; a 500 ms debounce collapses editor double-writes. On reload, the manager computes a diff against the current backend set:

- **Added** entry → start + initialize + register.
- **Removed** entry → deregister + stop.
- **Modified** entry → remove-then-add.

Failed starts are logged but do not roll back successful starts.

### Decision: Structured logs via `structlog`, JSON renderer to stdout

JSON on stdout is the simplest log sink that works for `journalctl`, Docker, `jq` pipelines, and log aggregators. `structlog` provides context binding so `request_id` flows through async call chains without explicit passing.

### Decision: MCP notifications → cache-refresh only

Backend-initiated notifications (e.g. `notifications/tools/list_changed`) trigger a re-`list_tools()` / `list_resources()` call to refresh the Registry, but the gateway does **not** push these to clients. Clients that need fresh data re-call `tools/list` themselves. This avoids re-implementing notification forwarding in the PoC while keeping the catalog consistent.

### Decision: Test stack — `pytest` + `pytest-asyncio` + `httpx.AsyncClient` + an in-process `FakeBackendConnection`

Three test layers:

- **Unit**: Registry, Router, config loader, middleware — no I/O.
- **Integration**: Gateway + `FakeBackendConnection` injected into the manager — exercises HTTP routing and JSON-RPC dispatch.
- **E2E**: Real stdio mock MCP server spawned as a subprocess, plus `httpx.AsyncClient` opening the SSE stream — proves the wire protocol works end-to-end.

Coverage target ≥ 80% overall, ≥ 90% on core modules.

## Risks / Trade-offs

- **Single event loop means blocking calls in one backend stall all routing.** → Backend adapters delegate to the SDK's async session, never to blocking I/O. CI test asserts no `time.sleep` or sync file I/O on the request path.
- **Stdio subprocess resource leaks on hot reload of a removed backend.** → `stop()` is wrapped in `asyncio.shield` + timeout; if it fails, the process is terminated forcibly and the manager logs the leak. Tests cover stop-under-error.
- **`watchfiles` may miss editor writes on some filesystems (e.g. NFS).** → Documented limitation; PoC targets local filesystems only.
- **No backpressure on slow backends** — a hung backend blocks its caller. → Out of scope for PoC; production would add per-backend timeouts and circuit breakers.
- **Prefix-based naming can produce surprising renames if a backend's internal tool name happens to contain `.`.** → Documented: tool names are split on the **first** `.`; backend names are validated to `^[a-z0-9_-]+$` to make this deterministic.
- **`mcp` SDK version drift** — future MCP spec changes may require SDK upgrades that change the `ClientSession` API. → Adapters are the only layer that imports the SDK; version upgrades are localized.
- **No persistent state means config is the only source of truth.** → Documented; restarts re-derive everything from YAML.

## Migration Plan

This is a greenfield project; there is no existing deployment to migrate. The rollout is:

1. Implement core modules per `tasks.md`.
2. Add `examples/mcp-gateway.yaml` and `examples/mock_backend.py` so a new contributor can run `uv run mcp-gateway --config examples/mcp-gateway.yaml` and immediately see two backends aggregated.
3. Validate with the acceptance checklist in `tasks.md` (Phase 6).

## Open Questions

- Should the gateway support the new MCP **Streamable HTTP** transport on the frontend (vs. legacy SSE-only)? → **Decision for PoC: support both** via FastAPI routes; the legacy SSE endpoint remains because most existing clients use it.
- Should tool results be cached (e.g. for read-only idempotent tools)? → **Deferred**; revisit if profiling shows backend latency is the bottleneck.
