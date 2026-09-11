## ADDED Requirements

### Requirement: Admin reload endpoint

The gateway SHALL expose `POST /admin/reload` at the same bind address as `GET /health`. The endpoint SHALL be reachable only from `127.0.0.1`; requests from non-loopback addresses SHALL be rejected with `403 Forbidden`. A successful reload SHALL return `200 OK` with a JSON body `{ "status": "applied", "added": [...], "removed": [...], "modified": [...] }`. A reload that succeeds but leaves one or more new backends unhealthy SHALL return `200 OK` with `{ "status": "partial", "failed": [...] }`.

#### Scenario: Admin reload triggers a re-read from the web backend

- **WHEN** a request to `POST /admin/reload` arrives from a loopback address while the gateway is in `web` config mode
- **THEN** the gateway re-fetches the backend set from the web package and applies the diff to `BackendConnectionManager`, returning the standard `applied` body

#### Scenario: Admin reload is rejected from non-loopback

- **WHEN** a request to `POST /admin/reload` arrives from a non-loopback address
- **THEN** the gateway returns `403 Forbidden` and does not touch the running backend set

#### Scenario: Admin reload is not available in YAML mode

- **WHEN** a request to `POST /admin/reload` arrives while the gateway is in YAML mode
- **THEN** the gateway returns `404 Not Found`