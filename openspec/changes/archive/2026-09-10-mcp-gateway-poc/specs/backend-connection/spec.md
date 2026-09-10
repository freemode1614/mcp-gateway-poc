## ADDED Requirements

### Requirement: Unified backend connection interface

The gateway SHALL define a single `BackendConnection` interface that all transport implementations implement, so that the rest of the system is transport-agnostic.

#### Scenario: Interface contract

- **WHEN** any backend adapter is used by the gateway
- **THEN** it SHALL expose `name`, `start()`, `stop()`, `healthcheck()`, `initialize()`, `list_tools()`, `call_tool(name, args)`, `list_resources()`, `read_resource(uri)`, and SHALL send/receive notifications over the same connection

### Requirement: Stdio backend starts and connects

The gateway SHALL start stdio backends as child processes and speak MCP JSON-RPC over their stdin/stdout using the official `mcp` SDK.

#### Scenario: Stdio backend connects and registers tools

- **WHEN** the gateway starts a stdio backend with a valid `command` and `args`
- **THEN** the process is spawned, the MCP `initialize` handshake completes, and `list_tools()` / `list_resources()` results are added to the Registry with the `<backend_name>.` prefix

#### Scenario: Stdio backend env vars are passed

- **WHEN** the backend config declares `env`
- **THEN** each declared variable is set in the child process environment, with `${env:VAR}` references interpolated from the gateway's environment

#### Scenario: Stdio startup failure marks backend unhealthy

- **WHEN** the child process exits before `initialize` completes within `startup_timeout_s`
- **THEN** the backend is marked `unhealthy`, no entry is added to the Registry, and the gateway continues to run

### Requirement: HTTP/SSE backend connects

The gateway SHALL connect to remote MCP servers over HTTP/SSE using the official `mcp` SDK `sse_client`.

#### Scenario: HTTP/SSE backend connects and registers tools

- **WHEN** the gateway connects to an `sse` backend with a valid `url`
- **THEN** the SSE stream is opened, `initialize` completes, and tools/resources are added to the Registry with the `<backend_name>.` prefix

#### Scenario: HTTP/SSE headers are forwarded

- **WHEN** the backend config declares `headers`
- **THEN** each header is sent on the initial SSE request

#### Scenario: HTTP/SSE connection failure marks backend unhealthy

- **WHEN** the SSE handshake fails or the server closes the stream
- **THEN** the backend is marked `unhealthy`, and the gateway continues to run

### Requirement: Backend crash triggers automatic restart

The gateway SHALL attempt to restart a crashed backend up to 3 times with exponential backoff (1s, 2s, 4s) before marking it `permanently_failed`.

#### Scenario: Backend recovers within retry window

- **WHEN** a backend process exits unexpectedly and restarts succeed on the second attempt
- **THEN** the backend's tools/resources are re-added to the Registry and subsequent requests route normally

#### Scenario: Backend exhausts retries

- **WHEN** a backend fails to restart 3 consecutive times
- **THEN** the backend is marked `permanently_failed` and is only re-attempted after a config reload
