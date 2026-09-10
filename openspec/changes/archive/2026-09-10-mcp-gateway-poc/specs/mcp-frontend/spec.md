## ADDED Requirements

### Requirement: MCP transport over HTTP/SSE and Streamable HTTP

The gateway SHALL expose MCP using the HTTP-with-SSE transport defined by the MCP specification, so that any MCP-compatible HTTP client can connect.

#### Scenario: Client opens the SSE stream

- **WHEN** a client sends `GET /sse` to the gateway
- **THEN** the gateway responds with `200 OK`, `Content-Type: text/event-stream`, and an `endpoint` event whose data is the absolute URL the client should POST JSON-RPC requests to

#### Scenario: Client sends a JSON-RPC request

- **WHEN** a client sends `POST /messages` with a JSON-RPC 2.0 body and `Accept: application/json, text/event-stream`
- **THEN** the gateway dispatches the request and returns either a JSON response (for `application/json` accept) or an SSE event stream (for `text/event-stream` accept), per MCP transport rules

#### Scenario: Server capabilities are advertised

- **WHEN** the client sends an `initialize` JSON-RPC request
- **THEN** the gateway responds with `serverInfo.name = "mcp-gateway"`, `serverInfo.version` matching the package version, and `capabilities` reflecting the union of all healthy backends' tools and resources

### Requirement: JSON-RPC method dispatch

The gateway SHALL route JSON-RPC methods to the correct internal handler and return JSON-RPC standard error codes on failure.

#### Scenario: tools/list returns unified catalog

- **WHEN** the client calls `tools/list`
- **THEN** the gateway returns the aggregated tools from the Registry without contacting any backend (catalog is cached in-memory)

#### Scenario: tools/call is routed by prefix

- **WHEN** the client calls `tools/call` with `params.name = "<backend>.<tool>"`
- **THEN** the gateway forwards the call to `<backend>` with the prefix stripped from the name and returns the backend's result unmodified

#### Scenario: resources/list returns unified catalog

- **WHEN** the client calls `resources/list`
- **THEN** the gateway returns the aggregated resources from the Registry, each with a URI prefixed by `<backend>://`

#### Scenario: resources/read is routed by URI

- **WHEN** the client calls `resources/read` with a `params.uri` whose scheme is `<backend>://`
- **THEN** the gateway routes the read to that backend with the URI scheme rewritten back to the backend's original scheme

#### Scenario: Unknown method returns -32601

- **WHEN** the client sends any JSON-RPC method the gateway does not implement
- **THEN** the gateway responds with `error.code = -32601` (`Method not found`) and a human-readable `error.message`

#### Scenario: Backend unavailable returns -32001

- **WHEN** the client calls `tools/call` or `resources/read` targeting a backend that is not registered or not healthy
- **THEN** the gateway responds with `error.code = -32001` (`Backend unavailable`) and the backend name in `error.message`

#### Scenario: Unknown tool returns -32601

- **WHEN** the client calls `tools/call` with a prefixed name that is not in the Registry
- **THEN** the gateway responds with `error.code = -32601` (`Method not found`) and the requested name in `error.message`
