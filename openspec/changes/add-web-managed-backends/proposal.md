## Why

Today, MCP backends are declared statically in `mcp-gateway.yaml`. Adding or
editing a backend requires editing the file and waiting for `ConfigWatcher`
to reload it. There is no audit trail, no concurrency safety, and the loop
"edit YAML → reload → observe logs" is awkward from a developer laptop or a
shared demo box. We want a real React SPA to list, create, edit, and delete
backends, persisted to PostgreSQL, with a "reload gateway" button that pushes
the new set into the gateway's existing `BackendConnectionManager`.

## What Changes

- Add a new top-level project `/web/` (sibling to `src/`, `tests/`, `docs/`).
  It owns two things:
  - A **React 18 + TypeScript SPA** built with Vite. Source lives in
    `/web/src/`, builds to `/web/dist/`. Data layer uses
    `@tanstack/react-query` for fetching, caching, and optimistic updates.
  - A **Python FastAPI service** at `packages/web-api/` (note: NOT
    under `/web/` — the Python service is in `packages/` to match
    AGENTS.md §7.1's target monorepo layout, and named `web-api` so
    it stays distinct from `/web/` which holds the Node SPA) that
    exposes CRUD endpoints for backends and serves the built SPA at
    `/admin/`. Talks to PostgreSQL via SQLAlchemy 2.x async +
    `asyncpg`. Runs Alembic migrations.
- A `docker-compose.yml` at the repo root runs PostgreSQL on a named volume,
  designed for OrbStack but portable to any Docker host.
- Extend `packages/mcp-gateway` (later: rename once we move to a real
  workspace) with `POST /admin/reload` that re-reads the backend set from
  the web's REST API and feeds it to `BackendConnectionManager.reload()`.
  The existing `ConfigWatcher` becomes the YAML-only path; when
  `MCP_GATEWAY_CONFIG_BACKEND=web` is set the watcher is skipped.
- Keep YAML loading as the default (`MCP_GATEWAY_CONFIG_BACKEND=yaml`) so the
  existing 92-test suite keeps working without a Postgres dependency. The
  `packages/web-api/` Python package is added as a dev dependency of the gateway
  only when the operator opts in.
- Web routes emit the same `request_id` middleware logs the rest of the
  gateway already emits (no new logging surface).

## Capabilities

### New Capabilities

- `web-ui`: A real React SPA (Vite + React 18 + TypeScript) for listing,
  creating, editing, and deleting backend entries, plus a "reload gateway"
  button that hits `POST /admin/reload`.
- `web-storage`: PostgreSQL persistence layer for backends, owned by
  `packages/web-api/`, with Alembic migrations and a docker-compose service for
  local dev (OrbStack).
- `web-api`: FastAPI REST API (`/api/backends`) that the SPA talks to.
  Lives in the same Python project (`packages/web-api/`) and also
  serves the built SPA at `/admin/`.

### Modified Capabilities

- `configuration`: Backend registration becomes available from two
  sources — the existing YAML file (unchanged behavior) or the new
  web-managed PostgreSQL store. The choice is made at startup via the
  `MCP_GATEWAY_CONFIG_BACKEND` env var; YAML remains the default.
- `mcp-frontend`: Add `POST /admin/reload` to the gateway's HTTP surface,
  guarded by a localhost-only check (matches the gateway's existing
  127.0.0.1 bind).
- `observability`: Web routes participate in the existing
  `RequestIDMiddleware` — no new logging contract, but the new endpoints
  MUST show up in `access` logs with the request_id propagated.

## Impact

- **New dependencies** (`packages/web-api/` Python): `fastapi`,
  `uvicorn`, `sqlalchemy>=2`, `asyncpg`, `alembic`, `python-multipart`,
  `httpx`. No Jinja2 / no templating engine — the SPA is a separate
  Node project.
- **New dependencies** (`/web/` Node): `react@19`, `react-dom`,
  `vite`, `@vitejs/plugin-react`, `typescript`, `@tanstack/react-query`,
  `react-router-dom@7`, plus dev deps for ESLint and Vitest.
- **New dev dependency** (root): nothing — `docker compose` is the only
  external requirement, plus Node.js ≥18 for the SPA toolchain.
- **Modified gateway**: 1 new endpoint (`/admin/reload`), 1 new env var,
  a thin `ConfigBackend` abstraction so YAML and web paths share the
  reload semantics. Estimated +120 lines, +30 lines of tests.
- **Modified CI**: The existing `make test` runs without Postgres (YAML
  path). A new `make test-web` target requires `docker compose up -d`.
- **Breaking change**: None. YAML remains the default; the web path is
  opt-in per process.