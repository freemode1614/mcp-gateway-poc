## ADDED Requirements

### Requirement: Web admin can list, create, edit, and delete backends

The web package SHALL expose a React SPA at `http://127.0.0.1:8080/admin/`
that lets a user list all configured backends, create a new backend, edit
an existing backend, and delete a backend. All four actions SHALL work
without a full page reload and SHALL show a success or error toast after
each mutation.

#### Scenario: List page shows all backends

- **WHEN** the user opens `/admin/`
- **THEN** the page renders one row per backend with `name`, `transport`,
  and a current health badge, fetched from `GET /api/v1/backends` and cached
  by TanStack Query

#### Scenario: Create form persists a new backend

- **WHEN** the user submits a valid create form
- **THEN** the SPA POSTs to `/api/v1/backends`, the new row appears in the
  table without a manual refresh, and a success toast is shown

#### Scenario: Edit form updates an existing backend

- **WHEN** the user submits the edit form for an existing backend
- **THEN** the SPA PUTs to `/api/v1/backends/{name}`, the row is updated
  in place, and a success toast is shown

#### Scenario: Delete removes the backend

- **WHEN** the user clicks the delete button on a backend row and
  confirms in a modal
- **THEN** the SPA DELETEs `/api/v1/backends/{name}`, the row disappears
  from the table, and a success toast is shown

#### Scenario: Invalid form re-renders with errors

- **WHEN** the user submits a create or edit form with an invalid
  backend name (e.g. contains uppercase letters) or a missing required
  field
- **THEN** the form re-renders with an error message naming the
  offending field and the mutation is NOT submitted

### Requirement: Reload button pushes the persisted set to the gateway

The web package SHALL expose a "Reload gateway" button on `/admin/` that,
when clicked, POSTs to `POST /api/reload` (which fans out to the
gateway's `POST /admin/reload`) and reports the gateway's response back
to the user as a toast.

#### Scenario: Reload succeeds

- **WHEN** the user clicks "Reload gateway" and the gateway returns 200
  OK with `{ "status": "applied" }`
- **THEN** the SPA shows a success toast stating which backends were
  added, removed, or restarted

#### Scenario: Reload returns a partial failure

- **WHEN** the user clicks "Reload gateway" and the gateway returns 200
  OK with `{ "status": "partial", "failed": ["<name>"] }`
- **THEN** the SPA shows a warning toast naming the failed backends and
  the table remains usable

#### Scenario: Reload endpoint is unreachable

- **WHEN** the user clicks "Reload gateway" and the gateway is not
  running
- **THEN** the SPA shows an error toast with a clear "gateway
unreachable" message and the rest of the page remains usable

### Requirement: Frontend is a real React SPA, not server-rendered HTML

The frontend SHALL be built with React 19 + TypeScript + Vite. The
backend SHALL serve the built SPA as static files under `/admin/`;
it SHALL NOT render HTML on the server. The SPA SHALL fetch and
mutate data over JSON, not via form posts to server-rendered routes.

#### Scenario: Pages work without JavaScript

- **WHEN** a user opens `/admin/` with JavaScript disabled
- **THEN** the page SHALL display a clear "this admin UI requires
  JavaScript" message rather than a broken page

#### Scenario: Vite dev server proxies API calls to the backend

- **WHEN** a developer runs `npm run dev` inside `/web/`
- **THEN** requests to `/api/*` and `/admin/reload` are proxied to
  `http://127.0.0.1:8080` so a single origin is used during
  development

#### Scenario: Production build is served by the backend

- **WHEN** the operator runs `npm run build` inside `/web/`
- **THEN** the resulting `dist/` directory is served by the FastAPI
  backend at `/admin/` as static files, with SPA fallback (any path
  not matching a static file or `/api/*` returns `dist/index.html`)

### Requirement: Frontend and backend live under `/web/` and `packages/web-api/`

The frontend project SHALL live at `/web/` at the repo root and the
backend project SHALL live at `packages/web-api/`. They SHALL be
siblings of `src/`, `tests/`, `docs/`, and `openspec/`. The backend
lives under `packages/` to follow the §7.1 monorepo target; the SPA
lives at the repo root because Node projects don't share the Python
workspace's tooling concerns (lock file, dev tooling, etc.). The
backend is named `web-api` (not just `web`) to keep it unambiguous
against the `/web/` SPA directory.

#### Scenario: Web directory shape

- **WHEN** the change is shipped
- **THEN** the repo root contains `/web/` (Node SPA) as a sibling of
  `src/`, `tests/`, `docs/`, and `openspec/`, and `packages/web-api/`
  (Python backend) lives under the existing `packages/` tree

#### Scenario: Each subproject has its own dependency manifest

- **WHEN** a developer wants to work on the backend only
- **THEN** they can `cd packages/web-api && uv pip install -e ".[dev]"`
  without touching Node, and vice versa for the frontend with
  `cd /web && npm install`

#### Scenario: Backend has no runtime dep on the gateway

- **WHEN** the web backend's runtime deps are installed
- **THEN** `mcp_gateway.*` SHALL NOT be imported; the backend talks
  to the gateway over HTTP only