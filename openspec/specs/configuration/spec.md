# configuration Specification

## Purpose
TBD - created by archiving change mcp-gateway-poc. Update Purpose after archive.
## Requirements
### Requirement: YAML configuration with documented schema

The gateway SHALL load its configuration from a YAML file whose schema is validated at startup.

#### Scenario: Default config locations are searched

- **WHEN** the gateway is started with no `--config` flag and `MCP_GATEWAY_CONFIG` env var unset
- **THEN** it searches `./mcp-gateway.yaml` then `~/.config/mcp-gateway/config.yaml` and uses the first file found

#### Scenario: Valid config loads

- **WHEN** the config file passes all validation rules
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

The gateway SHALL interpolate `${env:VAR}` placeholders in `env` and `headers` values from the gateway's own environment at startup.

#### Scenario: Variable is substituted

- **WHEN** a backend declares `env: { GITHUB_TOKEN: "${env:GITHUB_TOKEN}" }` and the env var is set
- **THEN** the child process receives the actual token value

#### Scenario: Missing variable fails fast

- **WHEN** a `${env:VAR}` placeholder references a variable that is not set
- **THEN** startup fails with an error naming the missing variable and the backend it was declared on

### Requirement: Hot reload applies config diff

The gateway SHALL watch the config file and apply changes (added, removed, or modified backends) without restarting.

#### Scenario: Adding a backend makes its tools visible

- **WHEN** the config file is edited to add a new backend and the debounce window elapses
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

- **WHEN** the config file is rewritten multiple times within `reload.debounce_ms`
- **THEN** only one reload is triggered after the debounce window expires

