# mcp-gateway

A local MCP Gateway that aggregates multiple MCP backend servers behind a single
HTTP/SSE endpoint. One client connection, all tools and resources from every
backend visible under a single namespace.

## Why

Most MCP clients only connect to one endpoint. With many MCP servers (GitHub,
Jira, custom internal tools), you end up with N separate client configurations
and no unified observability. `mcp-gateway` solves this by acting as a local
proxy:

```
Client ──HTTP/SSE──▶ mcp-gateway ──┬─ stdio subprocess  ─▶ Backend A
                                   └─ HTTP/SSE          ─▶ Backend B
```

Each backend's tools/resources are exposed with a `<backend>.` prefix so
callers always know which backend is answering.

## Features (PoC scope)

- HTTP/SSE frontend on `127.0.0.1` (default port 8765)
- Backend transports: **stdio subprocess** and **HTTP/SSE**
- Aggregated tool and resource catalogs
- `<backend>.<tool>` and `<backend>://<resource>` namespace
- YAML configuration with `${env:VAR}` interpolation
- Hot reload on config edit (add/remove/restart diffed, others unaffected)
- Structured JSON logging with `request_id` propagation
- `GET /health` for per-backend status
- Structured lifecycle logs (`startup`, `backend_connected`, `reload_applied`, …)

Out of scope for the PoC: authentication, prompts/sampling, persistent state,
multi-tenant quotas.

## Install

Requires Python 3.13 and [uv](https://docs.astral.sh/uv/).

```bash
uv venv
uv pip install -e ".[dev]"
```

## Quick start (two commands)

Terminal 1 — start the gateway with the example config:

```bash
export PYTHON="$(pwd)/.venv/bin/python"   # so the stdio mock can import `mcp`
mcp-gateway --config examples/mcp-gateway.yaml
```

Terminal 2 — query the gateway:

```bash
curl http://127.0.0.1:8765/health

# JSON-RPC initialize
curl -X POST http://127.0.0.1:8765/messages \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}'

# List tools (prefixed with backend name)
curl -X POST http://127.0.0.1:8765/messages \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}'

# Call a tool (note the "mock." prefix)
curl -X POST http://127.0.0.1:8765/messages \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"mock.add","arguments":{"a":2,"b":3}}}'
```

Open the SSE stream:

```bash
curl -N http://127.0.0.1:8765/sse
```

The first event is `event: endpoint` with the absolute URL to POST to.

## Configuration

```yaml
gateway:
  host: 127.0.0.1
  port: 8765
  log_level: info
  reload:
    enabled: true
    debounce_ms: 500

backends:
  - name: github               # unique, used as tool prefix
    transport: stdio
    command: uvx
    args: [mcp-server-github]
    env:
      GITHUB_TOKEN: "${env:GITHUB_TOKEN}"

  - name: jira
    transport: sse
    url: http://127.0.0.1:9001/sse
    headers:
      Authorization: "Bearer ${env:JIRA_TOKEN}"
```

Backend `name` must match `^[a-z0-9_-]+$`. Edit the file while the gateway is
running — within the debounce window, the gateway will add / remove / restart
the affected backends and emit a `reload_applied` log line.

## CLI flags

- `--config <path>`: explicit config file (else: `MCP_GATEWAY_CONFIG` env var,
  `./mcp-gateway.yaml`, `~/.config/mcp-gateway/config.yaml`)
- `--host <host>`: override `gateway.host`
- `--port <port>`: override `gateway.port`
- `--log-level <level>`: override `gateway.log_level`

## Tests

```bash
uv run pytest            # 78 tests, all layers
uv run pytest --cov=src/mcp_gateway   # with coverage report
```

Coverage targets for the PoC: ≥ 80% overall, ≥ 90% on `src/mcp_gateway/core/`.

## Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                         MCP Gateway (PoC)                            │
│   ┌─────────────────────────────────────────────────────────────┐    │
│   │ Frontend (FastAPI)                                           │    │
│   │   GET  /sse       → SSE stream (MCP transport)              │    │
│   │   POST /messages  → JSON-RPC dispatcher                      │    │
│   │   GET  /health     → per-backend status                      │    │
│   └─────────────────────────────────────────────────────────────┘    │
│   ┌─────────────────────────────────────────────────────────────┐    │
│   │ Core                                                          │    │
│   │   Registry     – in-memory catalog, tools/resources          │    │
│   │   Router       – dispatch tools/call, resources/read         │    │
│   │   Manager      – start/stop backends, hot-reload diff         │    │
│   └─────────────────────────────────────────────────────────────┘    │
│   ┌─────────────────────────────────────────────────────────────┐    │
│   │ Backend adapters                                             │    │
│   │   StdioBackend       → mcp.client.stdio.stdio_client         │    │
│   │   HttpSseBackend     → mcp.client.sse.sse_client             │    │
│   └─────────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────┘
```

Boundary rules:

- **Frontend only speaks MCP wire protocol** — knows nothing about backends.
- **Registry / Router are transport-agnostic** — they only see prefixed names.
- **Adapters are the only layer that imports the `mcp` SDK** — upgrades are local.

## Spec / plan

The gateway's domain contracts live in `openspec/specs/` as five
specifications (`backend-connection`, `configuration`, `mcp-frontend`,
`observability`, `registry-routing`). Inspect or validate them with:

```bash
openspec list --specs
openspec show <spec-name>
openspec validate <spec-name>
```

The original change proposal that produced these specs is preserved at
[`openspec/changes/archive/2026-09-10-mcp-gateway-poc/`](openspec/changes/archive/2026-09-10-mcp-gateway-poc/)
for historical reference. Active change proposals (e.g. the in-flight
`add-web-managed-backends`) are listed by `openspec list` and inspected
with `openspec show <change-name>`.