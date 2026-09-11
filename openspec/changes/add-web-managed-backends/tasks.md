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

## 4. Docker Compose for local Postgres

- [ ] 4.1 Add `docker-compose.yml` at the repo root with one `postgres:16-alpine` service, named volume `mcp-gateway-pg-data`, port mapping `127.0.0.1:5432:5432`, env from `.env`.
- [ ] 4.2 Add `make db-up` target that runs `docker compose up -d postgres` and `make db-down` that tears it down.
- [ ] 4.3 Verify a clean OrbStack install: `make db-up && make db-migrate && make -C packages/web-api run` connects and serves `/admin/`.

## 5. `/web/` — React SPA

- [ ] 5.1 Add runtime deps: `react@19`, `react-dom@19`, `react-router-dom@7`, `@tanstack/react-query`, `openapi-typescript`, `clsx`. Dev deps: `vitest`, `@testing-library/react`, `@testing-library/jest-dom`, `eslint`, `@typescript-eslint/*`, `prettier`.
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