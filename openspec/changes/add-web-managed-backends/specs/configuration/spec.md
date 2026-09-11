## MODIFIED Requirements

### Requirement: YAML configuration with documented schema

The gateway SHALL load its configuration from a YAML file whose schema is validated at startup. When `MCP_GATEWAY_CONFIG_BACKEND=web` is set, the gateway SHALL skip YAML loading entirely and instead fetch its backend set from the web package's HTTP API at startup.

#### Scenario: Default config locations are searched

- **WHEN** the gateway is started with no `--config` flag and `MCP_GATEWAY_CONFIG` env var unset and `MCP_GATEWAY_CONFIG_BACKEND` unset (or `yaml`)
- **THEN** it searches `./mcp-gateway.yaml` then `~/.config/mcp-gateway/config.yaml` and uses the first file found

#### Scenario: Web backend is selected via env var

- **WHEN** the gateway is started with `MCP_GATEWAY_CONFIG_BACKEND=web` and `MCP_GATEWAY_WEB_URL=http://127.0.0.1:8080`
- **THEN** the YAML path is skipped and the gateway fetches the backend set from `GET {MCP_GATEWAY_WEB_URL}/api/backends`

#### Scenario: Valid config loads

- **WHEN** the config source (YAML or web) returns a payload that passes all validation rules
- **THEN** the gateway starts with the declared `gateway.host`, `gateway.port`, and `backends` list

#### Scenario: Invalid backend name rejected

- **WHEN** a backend `name` does not match `^[a-z0-9_-]+$`
- **THEN** startup fails with a clear error pointing at the offending entry

#### Scenario: Duplicate backend name rejected

- **WHEN** two entries in `backends` share the same `name`
- **THEN** startup fails with a duplicate-name error

#### Scenario: Missing required field rejected

- **WHEN** a `stdio` backend has no `command` or an `sse` backend has no `url`
- **THEN** startup fails with a schema-validation error naming the field and backend

#### Scenario: Invalid port rejected

- **WHEN** `gateway.port` is outside `[1, 65535]` or `gateway.host` is empty
- **THEN** startup fails with a validation error

### Requirement: Environment variable interpolation

The gateway SHALL interpolate `${env:VAR}` placeholders in `env`, `headers`, `command`, `args`, and `url` values from the gateway's own environment at startup. The same interpolation SHALL run regardless of whether the config came from YAML or the web backend.

#### Scenario: Variable is substituted

- **WHEN** a backend declares `env: { GITHUB_TOKEN: "${env:GITHUB_TOKEN}" }` and the env var is set
- **THEN** the child process receives the actual token value

#### Scenario: Missing variable fails fast

- **WHEN** a `${env:VAR}` placeholder references a variable that is not set
- **THEN** startup fails with an error naming the missing variable and the backend it was declared on

### Requirement: Hot reload applies config diff

The gateway SHALL watch the config source and apply changes (added, removed, or modified backends) without restarting. When the source is YAML the existing `ConfigWatcher` debounce loop is used; when the source is the web backend the gateway SHALL accept `POST /admin/reload` as the reload trigger and SHALL NOT watch a file.

#### Scenario: Adding a backend makes its tools visible

- **WHEN** the config source is updated to add a new backend and the reload trigger fires
- **THEN** the backend is started, its tools/resources appear in subsequent `tools/list` and `resources/list` responses, and the gateway emits a `reload_applied` log line

#### Scenario: Removing a backend stops it cleanly

- **WHEN** an entry is removed from `backends`
- **THEN** that backend is stopped, its tools/resources are removed from the Registry, and remaining backends are unaffected

#### Scenario: Modifying a backend restarts it

- **WHEN** an existing entry's `command`, `args`, `url`, `env`, or `headers` change
- **THEN** the backend is treated as a remove-then-add: stopped, restarted with new config, and re-registered

#### Scenario: Failed reload leaves other backends untouched

- **WHEN** the new config introduces a backend that fails to start
- **THEN** the failed backend is reported in logs as `unhealthy` and all previously-healthy backends continue serving requests

#### Scenario: Debounce prevents editor double-fires

- **WHEN** the YAML config file is rewritten multiple times within `reload.debounce_ms`
- **THEN** only one reload is triggered after the debounce window expires

#### Scenario: Web backend reload is idempotent

- **WHEN** `POST /admin/reload` is called with the same backend set as the currently running one
- **THEN** the gateway returns `{ "status": "applied", "added": [], "removed": [], "modified": [] }` and does not restart any backend

## ADDED Requirements

### Requirement: Configuration backend is selectable at startup

The gateway SHALL accept a `MCP_GATEWAY_CONFIG_BACKEND` env var with two valid values: `yaml` (default, current behavior) and `web`. When `web` is set, the gateway SHALL additionally accept `MCP_GATEWAY_WEB_URL` pointing at the web package's HTTP API.

#### Scenario: Default backend is YAML

- **WHEN** the gateway starts with `MCP_GATEWAY_CONFIG_BACKEND` unset
- **THEN** it behaves identically to previous versions: YAML is loaded, `ConfigWatcher` is started, and `POST /admin/reload` returns 404

#### Scenario: Web backend requires a URL

- **WHEN** `MCP_GATEWAY_CONFIG_BACKEND=web` is set but `MCP_GATEWAY_WEB_URL` is unset
- **THEN** startup fails with a clear error naming the missing env var

#### Scenario: Web backend does not start the file watcher

- **WHEN** the gateway starts with `MCP_GATEWAY_CONFIG_BACKEND=web`
- **THEN** no `watchfiles` observer is created and no inotify-style file events are consumed