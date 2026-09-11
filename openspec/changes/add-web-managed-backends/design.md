## Context

`mcp-gateway-poc` is a single-package FastAPI service that aggregates MCP
backends behind one HTTP/SSE endpoint, configured from a YAML file watched
by `watchfiles`. We want a real React SPA to manage backends without
touching YAML: list/create/edit/delete entries, persisted to PostgreSQL,
and a "reload gateway" button that pushes the new set into the running
gateway process through a new HTTP endpoint. Local dev runs on OrbStack;
the compose file should be portable to any Docker host.

The SPA replaces a previously-discussed Jinja2 server-rendered approach.
The user wants a real client-side React app, so the frontend is its own
Node project rather than templates rendered by FastAPI.

## Goals / Non-Goals

**Goals:**
- A real React 18 SPA built with Vite + TypeScript. No templates, no
  Jinja2 — the SPA is served as static files by the backend.
- `/web/` (Node SPA) lives at the repo root as a sibling of `src/`,
  `tests/`, `docs/`, `openspec/`. The Python service lives at
  `packages/web-api/` (NOT under `/web/` — it's in `packages/` to match
  AGENTS.md §7.1's target monorepo layout and to be reachable via the
  future `uv` workspace). The two together form the "web UI" project,
  but they live in different trees because one is Node and one is Python.
- `packages/web-api/` is a Python service that:
  - Exposes `GET/POST/PUT/DELETE /api/backends` and `POST /api/reload`
    for the SPA.
  - Serves the built SPA at `/admin/` (single-page-app fallback).
  - Talks to PostgreSQL via SQLAlchemy 2.x async + `asyncpg`.
  - Runs Alembic migrations on demand.
- `/web/` is a Vite SPA that:
  - Lists backends in a table with create / edit / delete actions.
  - Hits `POST /api/reload` for the "Reload gateway" button.
  - Uses `@tanstack/react-query` for fetching and optimistic mutations.
  - Routes via `react-router-dom` (a single `/admin` route is enough
    for the MVP; routing is included so later pages don't require a
    refactor).
- One new gateway endpoint (`POST /admin/reload`) gated by loopback.
- Zero regression on the existing 92-test suite: YAML remains default
  and Postgres is not required for `make test`.

**Non-Goals:**
- Authentication, multi-user, RBAC, audit log (deferred to a later change).
- Tool catalog browser view (separate spec, deferred).
- Live WebSocket / SSE view of registry state.
- Production deployment story for any of the three services.
- HTTPS / reverse proxy setup.
- Converting the repo to a `uv` workspace. Today's layout is
  compatible with a future workspace — when that lands, `/web/`
  becomes `packages/web-frontend/` and `packages/web-api/` is reachable
  via the workspace's `members = ["packages/*"]`. Today's layout keeps
  the diff small.

## Decisions

### D1: `/web/` for the SPA at the repo root, `packages/web-api/` for the Python backend

**Choice:** The SPA lives at `/web/` (single Vite project at the
repo root, sibling to `src/`, `tests/`, `docs/`, `openspec/`). The
Python backend lives at `packages/web-api/` (adjacent to the gateway
package in the `packages/` tree). The two together form the "web UI"
project, but live in different trees because one is Node and one is
Python.

**Why:** Keeps the change small and the diff readable. The existing
gateway lives at `src/mcp_gateway/` (not yet in `packages/`); adding
a `packages/web-api/` sibling sets up the AGENTS.md §7.1 monorepo
target without forcing the gateway to relocate in the same change.
The SPA stays at the repo root because Node projects don't share the
Python workspace's tooling concerns (lock file, dev tooling, version
pins). Naming the Python side `web-api` (not just `web`) keeps it
  unambiguous against `/web/` — when both end up under `packages/`
  as `web-frontend` and `web-api`, no rename is needed.

**Alternative considered:** Put everything under `packages/web-api/` and
introduce the `uv` workspace now. Cleaner end state, but drags the
gateway relocation into the same change and turns a 47-checkbox task
list into a much bigger refactor.

### D2: React 19 SPA built with Vite + TypeScript

**Choice:** `/web/` is a Vite project. `npm create vite@latest
-- --template react-ts` is the scaffold; we add `@tanstack/react-query`,
`react-router-dom@7`, ESLint, Vitest on top.

**Why:** Vite gives us sub-second dev rebuilds and a single `dist/`
output that the backend can serve as static files. React 19 is the
current stable and brings the new compiler-friendly features (Actions,
`use()` hook, ref-as-prop) we want available even if the MVP doesn't
exercise them. TypeScript catches the shape mismatches between the SPA
and the backend's Pydantic models at build time.

**Alternative considered:** Next.js 15. Skipped because it drags in a
Node server we don't need for a single-page admin UI, and we'd have to
explain the SSR vs SPA choice in docs.

### D3: TanStack Query for data fetching

**Choice:** All backend calls go through `@tanstack/react-query`. No
hand-rolled `useEffect`+fetch.

**Why:** TanStack Query handles loading/error/refetch states, request
deduplication, and optimistic updates (which we want for the
"Reload gateway" button: flip a local cache entry to "reloading…" before
the round trip completes). One dependency covers what we'd otherwise
reimplement for every screen.

**Alternative considered:** Plain fetch + `useState`. Fine for one
screen, doesn't scale to "list + create modal + edit modal + reload
toast" without ceremony.

### D4: React Router 7 for the single `/admin` route

**Choice:** `react-router-dom@7` with one route at `/admin` and a
single `<BackendsPage />`. 404 routes fall through to a "not found"
component.

**Why:** A single page is enough for the MVP, but starting with a
router means later pages (`/admin/health`, `/admin/tools`) don't
require restructuring. The router adds ~5 KB to the bundle; worth it.

**Alternative considered:** No router, just a single `<App />`.
Cheaper, but a future addition of a second page requires a one-shot
refactor that the router pre-empts.

### D5: FastAPI backend at `packages/web-api/`, NOT under `src/` or `/web/`

**Choice:** The Python service is a stand-alone project at
`packages/web-api/` with its own `pyproject.toml`, `src/web_backend/`,
tests, and Alembic config. It is NOT placed inside `src/` (which is
the gateway's package layout) and not under `/web/` (which is the
SPA's Node project tree).

**Why:** The Python backend is a separate service with its own entry
point and tests. Mixing it into the gateway's `src/` would create a
circular layout (the gateway's `packages/mcp-gateway` is in
`src/mcp_gateway/`, but `src/` is one tree — putting a different
service there violates the "one service per `src/`" convention).
Mixing it under `/web/` would mix Node and Python projects under the
same directory, which makes the toolchain boundary unclear. A
dedicated `packages/web-api/` matches AGENTS.md §7.1 and is
reachable via the future `uv` workspace. The `web-api` suffix
distinguishes it from `/web/` (the SPA), so when both eventually land
under `packages/` as `web-frontend` and `web-api`, no rename is
needed.

**Alternative considered:** A `pyproject.toml` at the repo root with
both the gateway and the web backend as two packages installed
side-by-side. Cleaner end state, but again expands the change scope.

### D6: SPA is built and served as static files by the FastAPI backend

**Choice:** `npm run build` produces `/web/dist/`. The backend mounts
that directory at `/admin/` and returns `/admin/index.html` for any
non-`/api/` GET request that doesn't match a static file (SPA
fallback). API endpoints live under `/api/`.

**Why:** Single port to remember (`http://127.0.0.1:8080`), no
CORS preflight, no separate static-file server in dev. The backend
already binds to a known port for the gateway client; serving the
SPA from the same process is the simplest production story too.

**Alternative considered:** Separate Vite dev server on a different
port with CORS. Cleaner for development (HMR), but introduces a CORS
allowlist we have to maintain and an extra process for operators to
manage.

### D7: SQLAlchemy 2.x async + Alembic

**Choice:** `packages/web-api/src/web_backend/db.py` uses
`sqlalchemy[asyncio]>=2` with `asyncpg`. Migrations via Alembic, run
on demand (`alembic upgrade head`), not on startup.

**Why:** SA 2.x's async API is mature and well-typed. Alembic keeps
schema changes reviewable. Skipping auto-create-on-startup means an
operator who forgot to migrate gets a clear error message instead of
a half-initialized DB.

**Alternative considered:** SQLModel — appealing because we already
use Pydantic, but it lags SA's async features and complicates
migrations. Picked SA directly.

### D8: One SQLAlchemy model, JSONB for `args` / `env` / `headers`

**Choice:** `Backend` model with `args`, `env`, `headers` typed as
JSONB (`sa.JSON` mapped to PostgreSQL JSONB). One row per backend.

**Why:** Mirrors the YAML schema 1:1; JSONB is indexable if we later
need it and round-trips cleanly with Pydantic. Avoids a child table
per list column.

**Alternative considered:** Three child tables (`backend_arg`,
`backend_env_var`, `backend_header`). More normalized, but the data
is always read/written whole — the join overhead buys nothing.

### D9: Loopback-only `POST /admin/reload`

**Choice:** The gateway checks `request.client.host` against
`127.0.0.1` and `::1`; non-loopback → `403 Forbidden`. In YAML mode
the route returns `404 Not Found`.

**Why:** Same trust model the gateway already applies (127.0.0.1
bind, no auth). The web backend sits on the same host. A real auth
layer is the deferred next change; for the PoC, loopback is the
boundary.

**Alternative considered:** Bearer token / signed URL. Out of scope;
can be added later without breaking this contract.

### D10: `MCP_GATEWAY_CONFIG_BACKEND` env var selects the source

**Choice:** `yaml` (default, current behavior) or `web`. When `web`,
the gateway requires `MCP_GATEWAY_WEB_URL`, skips YAML loading,
skips the file watcher, and exposes `POST /admin/reload`.

**Why:** The existing YAML path is the source of truth for the test
suite. Adding a new path behind an env var keeps the 92 existing
tests green without a Postgres fixture.

**Alternative considered:** Always check both. Means both the file
and the DB are sources of truth, which leads to "which one won?"
bugs. Picked one-or-the-other.

### D11: docker-compose service, not a managed cluster

**Choice:** A single `postgres:16-alpine` service in
`docker-compose.yml` at the repo root, with a named volume
`mcp-gateway-pg-data`. No replicas, no init containers beyond the
standard `POSTGRES_*` env wiring.

**Why:** OrbStack (and Docker Desktop) treat a single compose
project as a first-class thing. A single Postgres on a volume
matches the PoC scale; HA Postgres is not the request.

**Alternative considered:** Embedded SQLite via `pglite` or
`pgserver-py`. Skipped because the spec wants real Postgres for the
JSONB ops and SQL observability.

## Risks / Trade-offs

- **R1: Two Python services and one Node service to run locally** →
  Mitigation: ship a top-level `make run-web` that brings up
  Postgres, builds the SPA, and starts the backend together. The
  gateway keeps its existing `make run`.
- **R2: Drift between `packages/web-api/` Pydantic models and the
  SPA's TypeScript types** → Mitigation: derive both from a shared
  JSON schema in `packages/web-api/openapi.json` (generated
  automatically by FastAPI's OpenAPI emitter). The SPA's types come
  from `openapi-typescript` at build time. A unit test in
  `packages/web-api/tests/` asserts the generated schema is valid.
- **R3: No auth means anyone on the box can hit `/admin/reload`** →
  Mitigation: document clearly; the deferred auth change is filed
  against the same `web-ui` capability.
- **R4: Alembic migrations need to be run before first launch** →
  Mitigation: backend startup fails fast with a clear message; the
  `make run-web` target runs `alembic upgrade head` before starting
  uvicorn.
- **R5: SPA bundle size will grow if we keep adding pages** →
  Mitigation: Vite's code-splitting per route is the default; we
  don't need to do anything yet. Document in the SPA README.

## Migration Plan

This is a green-field change with no existing data:

1. **Day 0 (ship):** Land the change. Repo gains `/web/`,
   `packages/web-api/`, `docker-compose.yml`, and `.env.example`.
   `make install` and `make test` work as before (YAML path).
2. **Day 1 (opt-in):** Operators who want the web run
   `docker compose up -d postgres`, `make -C packages/web-api migrate`,
   `make -C web build` (or `make -C web dev`),
   then `make -C packages/web-api run`, and start the gateway with
   `MCP_GATEWAY_CONFIG_BACKEND=web`.
3. **Rollback:** Set `MCP_GATEWAY_CONFIG_BACKEND=yaml` (or unset)
   and restart the gateway. `/web/` and `packages/web-api/`
   stay installed but are unused; deleting them requires removing
   the directory trees and the `docker-compose.yml` entry.

## Open Questions

- **Q1:** Should the SPA also expose the gateway's tool catalog on a
  read-only `/admin/tools` route, or wait until the catalog-browser
  change lands? (Current design: no; the SPA only manages the
  registry.)
- **Q2:** Do we want the SPA's Vite dev server to proxy
  `/api/*` and `/admin/reload` to the backend, so a developer can
  use `npm run dev` without a separate uvicorn? (Current design:
  yes — the Vite config gets a proxy entry in the SPA scaffold
  task.)
- **Q3:** Volume name — `mcp-gateway-pg-data` vs the OrbStack
  convention of `<project>_<service>_data`. Pick whichever the team
  prefers; default to `mcp-gateway-pg-data` so it's portable across
  compose implementations.