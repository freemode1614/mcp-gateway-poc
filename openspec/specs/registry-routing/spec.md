# registry-routing Specification

## Purpose
TBD - created by archiving change mcp-gateway-poc. Update Purpose after archive.
## Requirements
### Requirement: Registry aggregates tools with backend prefix

The gateway SHALL merge tools from all healthy backends into a single in-memory catalog, with each tool's name prefixed by `<backend_name>.`.

#### Scenario: Prefix is applied uniformly

- **WHEN** a backend exposes a tool named `create_issue`
- **THEN** the Registry stores it as `prefixed_name = "<backend>.create_issue"` and `real_name = "create_issue"`, and `tools/list` returns the prefixed name

#### Scenario: Prefix isolates same-named tools across backends

- **WHEN** two backends `github` and `jira` both expose a tool named `create_issue`
- **THEN** both are registered as `github.create_issue` and `jira.create_issue` with no collision

#### Scenario: Backend removal clears its entries

- **WHEN** a backend is stopped (manually, via crash exhaustion, or via config reload)
- **THEN** all of its tools and resources are removed from the Registry atomically

### Requirement: Router dispatches tools/call by prefix

The gateway SHALL resolve `tools/call` requests by parsing the `<backend>.<tool>` prefix and forwarding to the matching backend with the prefix stripped.

#### Scenario: Successful routing strips the prefix

- **WHEN** the client calls `tools/call` with `name = "github.create_issue"` and arguments `{"title": "x"}`
- **THEN** the Router invokes `backend["github"].call_tool("create_issue", {"title": "x"})` and returns the result

#### Scenario: Unknown tool returns error

- **WHEN** the client calls `tools/call` with a prefixed name not present in the Registry
- **THEN** the Router raises `UnknownToolError`, which the frontend translates to JSON-RPC `-32601`

#### Scenario: Unhealthy backend returns error

- **WHEN** the Router resolves the prefix to a backend whose session is currently unhealthy
- **THEN** the Router raises `BackendUnavailableError`, which the frontend translates to JSON-RPC `-32001`

### Requirement: Router dispatches resources/read by URI

The gateway SHALL route `resources/read` requests by matching the URI scheme against configured backend names.

#### Scenario: Successful resource read

- **WHEN** the client calls `resources/read` with `uri = "github://repo/readme"`
- **THEN** the Router invokes `backend["github"].read_resource("repo/readme")` (scheme stripped) and returns the result

#### Scenario: Unknown URI scheme returns error

- **WHEN** the client calls `resources/read` with a URI whose scheme matches no backend
- **THEN** the Router raises `UnknownResourceError`, translated to JSON-RPC `-32601`

