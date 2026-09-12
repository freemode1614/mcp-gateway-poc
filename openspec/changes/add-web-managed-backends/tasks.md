## 1. Scaffold the two-subproject layout

- [ ] 1.1 Create `packages/web-api/` with `pyproject.toml`, `src/web_backend/__init__.py`, `src/web_backend/app.py`, `src/web_backend/db.py`, `src/web_backend/models.py`, `src/web_backend/schemas.py`. Build backend: hatchling; wheel target `packages = ["src/web_backend"]`.
- [ ] 1.2 Create `/web/` (single Vite project at the repo root) via `npm create vite@latest -- --template react-ts` (or hand-rolled equivalent with `package.json`, `vite.config.ts`, `tsconfig.json`, `index.html`, `src/main.tsx`, `src/App.tsx`).
- [ ] 1.3 Add `.env.example` at the repo root with `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `DATABASE_URL`.
- [ ] 1.4 Add `.gitignore` entries for `/web/node_modules/`, `/web/dist/`, `packages/web-api/.venv/`.

## 2. `packages/web-api/` — Python service

- [ ] 2.1 Pin runtime deps in `packages/web-api/pyproject.toml`: `fastapi>=0.115`, `uvicorn[standard]>=0.32`, `sqlalchemy[asyncio]>=2`, `asyncpg`, `alembic`, `python-multipart`, `httpx>=0.27`, `pydantic>=2.9`. Dev deps: `pytest>=8.3`, `pytest-asyncio>=0.24`, `respx`.
- [ ] 2.2 Implement `web_backend/models.py` with the `Backend` SQLAlchemy model (id UUID, name unique slug, transport Enum, command, args/env/headers JSON, url, startup_timeout_s, created_at, updated_at).
- [ ] 2.3 Implement `web_backend/schemas.py` with `BackendIn` / `BackendOut` Pydantic models, validating against `packages/web-api/openapi.json`.
- [ ] 2.4 Implement `web_backend/db.py` with async engine factory, `get_session` dependency, and a `verify_schema()` startup check that fails fast if the `backends` table is missing.
- [ ] 2.5 Implement `web_backend/app.py` with FastAPI app, CORS allowing the Vite dev origin, and routers for `/api/backends` (list/create/get/put/delete) and `/api/reload`.
- [ ] 2.6 Mount the SPA at `/admin/`: serve `/web/dist/` if it exists, otherwise return a clear "frontend not built" message. Add SPA fallback so unknown `/admin/*` paths return `index.html`.
- [ ] 2.7 Unit tests in `packages/web-api/tests/unit/` covering model, schemas, and CRUD routes (with `httpx.AsyncClient(transport=ASGITransport)` and an in-memory SQLite engine for isolation).
- [ ] 2.8 Integration tests in `packages/web-api/tests/integration/` for `POST /api/reload` against a stubbed gateway server (use `respx` to mock httpx).

## 3. Alembic migrations

- [ ] 3.1 Add `alembic.ini` and `packages/web-api/alembic/env.py` wired to `DATABASE_URL` from env.
- [ ] 3.2 Write the initial migration creating `backends` with the unique index on `name` and the JSON columns.
- [ ] 3.3 Document `make -C packages/web-api migrate` and add the target to the root Makefile.
- [ ] 3.4 Verify `alembic upgrade head` on a fresh Postgres creates the table and matches the model.

## 4. Docker Compose (Postgres + web-api + gateway, single file)

- [ ] 4.1 Add `docker-compose.yml` at the repo root with three services: `postgres` (`postgres:16-alpine`, named volume `mcp-gateway-pg-data`, port `127.0.0.1:5432:5432`), `web-api` (builds from `packages/web-api/Dockerfile`, port `127.0.0.1:8080:8080`, depends_on postgres with a healthcheck), and `gateway` (builds from `packages/mcp-gateway/Dockerfile`, port `127.0.0.1:8765:8765`, depends_on web-api with a healthcheck, env `MCP_GATEWAY_CONFIG_BACKEND=web`, `MCP_GATEWAY_WEB_URL=http://web-api:8080`). All env wired from `.env`.
- [ ] 4.2 Add `make db-up` target that runs `docker compose up -d postgres` (just Postgres for local dev without containers) and `make up` that brings up all three. Add `make down` and `make logs`.
- [ ] 4.3 Verify a clean OrbStack install: `make up` brings everything, the gateway's `/health` returns "ok", `curl http://127.0.0.1:8080/admin/` returns the SPA's index.html.

## 5. `/web/` — React SPA

- [ ] 5.1 Add runtime deps: `react@19`, `react-dom@19`, `react-router-dom@8`, `@tanstack/react-query`, `openapi-typescript`, `clsx`. Dev deps: `vitest`, `@testing-library/react`, `@testing-library/jest-dom`, `@biomejs/biome`.
- [ ] 5.1a Add a `biome.json` at `/web/` with the project's recommended rule set (correctness + style + a11y), single quotes, 2-space indent, trailing commas; add `biome-ignore` comments only for documented exceptions.
- [ ] 5.1b Add `npm run lint` and `npm run format` scripts that invoke `biome check` and `biome format --write` respectively; wire `make lint-web` and `make format-web` in the root Makefile so the SPA's quality gates mirror the gateway's.
- [ ] 5.2 Configure `vite.config.ts` with a dev proxy: `/api/*` and `/admin/reload` forwarded to `http://127.0.0.1:8080`.
- [ ] 5.3 Set up `src/main.tsx` with `QueryClientProvider`, `BrowserRouter`, and a single `<App />` route at `/admin`.
- [ ] 5.4 Build `src/api/client.ts`: typed `fetch` wrappers generated from `packages/web-api/openapi.json` via `openapi-typescript`.
- [ ] 5.5 Build `src/api/queries.ts`: TanStack Query hooks (`useBackends`, `useCreateBackend`, `useUpdateBackend`, `useDeleteBackend`, `useReloadGateway`) with optimistic updates for mutations.
- [ ] 5.6 Build `src/pages/BackendsPage.tsx`: table of backends with health badges, "New" button, per-row edit/delete actions, "Reload gateway" button.
- [ ] 5.7 Build `src/components/{BackendForm, BackendTable, Toast, ConfirmModal}.tsx` and a `src/components/NoJS.tsx` fallback for users without JavaScript.
- [ ] 5.8 Wire `npm run gen-api` to fetch `/openapi.json` from a running backend and emit `src/api/schema.ts`. Wire `npm run build` to run `gen-api` first.
- [ ] 5.9 Unit tests with Vitest + Testing Library for the form validation, table rendering, and toast component.

## 6. Gateway: `POST /admin/reload`

- [ ] 6.1 Add `MCP_GATEWAY_CONFIG_BACKEND` env var (`yaml` default, `web` opt-in) and `MCP_GATEWAY_WEB_URL` to the gateway's `ConfigBackend` abstraction.
- [ ] 6.2 Implement `WebConfigSource` in the gateway that fetches `GET {MCP_GATEWAY_WEB_URL}/api/backends` at startup and on every `POST /admin/reload`.
- [ ] 6.3 Add `/admin/reload` route in `packages/mcp-gateway/src/mcp_gateway/frontend/app.py` returning 404 in YAML mode.
- [ ] 6.4 In web mode, the handler fetches via `WebConfigSource`, calls `BackendConnectionManager.reload(new_config)`, and returns `{ "status": "applied"|"partial", "added": [...], "removed": [...], "modified": [...], "failed": [...] }`.
- [ ] 6.5 Loopback guard: non-loopback `request.client.host` → 403; covered by a unit test.
- [ ] 6.6 Skip `ConfigWatcher` startup when `ConfigBackend.WEB` is selected; log `config_backend_selected` with the chosen backend and source URL.
- [ ] 6.7 Ensure `RequestIDMiddleware` covers `/admin/reload`; covered by a unit test asserting the log line shape.
- [ ] 6.8 Add unit tests for `ConfigBackend` env-var parsing and an integration test for `WebConfigSource` against a stubbed HTTP server.

## 7. Cross-project integration tests

- [ ] 7.1 Add `packages/web-api/tests/integration/test_gateway_e2e.py` that starts the gateway with `MCP_GATEWAY_CONFIG_BACKEND=web` and a stubbed web backend URL, then asserts that `POST /admin/reload` triggers a config refresh.
- [ ] 7.2 Add a root-level `make test-web` target that runs the `packages/web-api` unit tests (skipped if `DATABASE_URL` is unreachable).
- [ ] 7.3 Update root `make test` to also run the `packages/web-api` unit tests; document that the e2e gateway+web test requires `make db-up`.

## 8. Documentation + handoff

- [ ] 8.1 Update root `README.md` with a "Web UI (optional)" section explaining the env vars and `docker compose up` step.
- [ ] 8.2 Add `/web/README.md` describing the two-subproject layout (`/web/` Node SPA + `packages/web-api/` Python API) and how to run each one.
- [ ] 8.3 Add `packages/web-api/README.md` with local-dev quickstart, migration command, and the SPA-fallback behavior.
- [ ] 8.4 Add `/web/README.md` (project-level) with the Vite dev proxy, `npm run gen-api`, and the build pipeline.
- [ ] 8.5 Update `AGENTS.md` only if a new layering rule appears (e.g. note that `packages/web-api/` follows §7.1's monorepo target, while `/web/` is intentionally outside the Python workspace).
- [ ] 8.6 Re-run `make format lint typecheck test` from the repo root and confirm: 92 gateway tests still pass, `packages/web-api` unit tests pass.
- [ ] 8.7 Archive the change via `openspec archive add-web-managed-backends --yes`.

## 9. Production deploy files

- [ ] 9.1 Add `packages/web-api/Dockerfile`: multi-stage build. Stage 1 (`node:22-alpine`) runs `npm ci && npm run build` inside `/web/` and copies `/web/dist/` into `/build/web/`. Stage 2 (`python:3.13-slim`) installs `packages/web-api/[web]` extras, copies the prebuilt SPA into `/app/static`, runs `uvicorn web_backend.app:app` on port 8080. Non-root user, `HEALTHCHECK` hitting `/healthz`.
- [ ] 9.2 Add `packages/mcp-gateway/Dockerfile`: single-stage `python:3.13-slim`, installs the gateway + the runtime deps needed for SSE backend, runs `mcp-gateway` on port 8765. Non-root user, `HEALTHCHECK` hitting `/health`.
- [ ] 9.3 Wire the two Dockerfiles into `docker-compose.yml` (task 4.1) under `build:` blocks pointing at each package's Dockerfile. Add `MCP_GATEWAY_CONFIG_BACKEND=web`, `MCP_GATEWAY_WEB_URL=http://web-api:8080`, `DATABASE_URL=postgresql+asyncpg://postgres:5432/mcp_gateway` and other env from `.env`.
- [ ] 9.4 Add `depends_on` healthchecks: gateway waits for web-api's `/healthz` to be 200 before starting; web-api waits for postgres' `pg_isready`. Document the timeout values in `docker-compose.yml` comments.
- [ ] 9.5 Add `make image-web-api` and `make image-gateway` that build each image separately (useful for CI), and `make push-web-api` / `make push-gateway` placeholders that take a `REGISTRY` env var.
- [ ] 9.6 Update root `README.md` "Web UI (optional)" section with a "Running everything in containers" subsection that documents `make up`, `make down`, and the `docker compose logs -f` debugging flow.
- [ ] 9.7 Verify end-to-end: from a clean shell, `git clone`, `cp .env.example .env`, `make up`, `curl http://127.0.0.1:8080/admin/` returns the SPA HTML, `curl http://127.0.0.1:8765/health` returns `{"status":"ok"}`, and editing a backend via the SPA causes a `POST /admin/reload` that the gateway logs as `reload_applied`.