## ADDED Requirements

### Requirement: REST API exposes CRUD over backends

The web backend SHALL expose a versioned REST API under `/api/v1/` for the
React SPA. Endpoints and payloads SHALL follow the documented OpenAPI schema
generated from the backend's FastAPI app.

#### Scenario: List returns all backends

- **WHEN** the SPA calls `GET /api/v1/backends`
- **THEN** the backend returns `200 OK` with a JSON array of every row
  in the `backends` table, shaped per the `BackendOut` Pydantic model

#### Scenario: Create persists a new backend

- **WHEN** the SPA calls `POST /api/v1/backends` with a valid `BackendIn`
  body
- **THEN** the backend inserts a row, returns `201 Created` with the
  new `BackendOut`, and the SPA's TanStack Query cache is updated

#### Scenario: Create rejects an invalid backend

- **WHEN** the SPA calls `POST /api/v1/backends` with an invalid
  `BackendIn` body (bad `name` slug, missing required field)
- **THEN** the backend returns `422 Unprocessable Entity` with a JSON
  body naming the offending fields

#### Scenario: Edit replaces the row

- **WHEN** the SPA calls `PUT /api/v1/backends/{name}` with a valid
  `BackendIn` body
- **THEN** the backend updates the row in place, returns `200 OK`
  with the updated `BackendOut`

#### Scenario: Edit 404s on unknown name

- **WHEN** the SPA calls `PUT /api/v1/backends/{name}` for a name that
  does not exist
- **THEN** the backend returns `404 Not Found`

#### Scenario: Delete removes the row

- **WHEN** the SPA calls `DELETE /api/v1/backends/{name}`
- **THEN** the backend deletes the row and returns `204 No Content`

### Requirement: Reload endpoint proxies to the gateway

The web backend SHALL expose `POST /api/v1/reload` which, in turn, POSTs
to the gateway's `POST /api/v1/gateway/reload` over HTTP. The web backend
SHALL pass through the gateway's response body and status code so
the SPA can surface it directly.

#### Scenario: Gateway applies the reload

- **WHEN** the SPA calls `POST /api/v1/reload` and the gateway returns
  `200 OK` with `{ "status": "applied" }`
- **THEN** the backend returns the same `200 OK` and body to the SPA

#### Scenario: Gateway unreachable

- **WHEN** the SPA calls `POST /api/v1/reload` and the gateway does not
  respond within 5 seconds
- **THEN** the backend returns `502 Bad Gateway` with a clear
  "gateway unreachable" JSON body

### Requirement: OpenAPI schema is the contract

The web backend SHALL expose its OpenAPI schema at `/openapi.json`
(FastAPI default). The frontend SHALL generate TypeScript types from
this schema at build time via `openapi-typescript` so the SPA and the
backend never disagree on payload shape.

#### Scenario: Build fetches the latest schema

- **WHEN** the SPA's `npm run build` runs
- **THEN** it fetches `/openapi.json` from a local backend (or from
  a checked-in snapshot in CI) and emits
  `/web/src/api/schema.ts`

#### Scenario: Schema drift fails the build

- **WHEN** the backend's Pydantic model changes in a way that
  invalidates an existing SPA usage
- **THEN** the SPA's TypeScript build fails with a clear error
  pointing at the affected endpoint