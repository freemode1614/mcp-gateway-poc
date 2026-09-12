# AGENTS.md — Engineering Guide for AI Agents & Contributors

This file governs **code quality**, **coding style** (Google Python Style), and **tooling** for the `mcp-gateway-poc` codebase. Both human contributors and AI coding agents **must** follow it.

## 0. Project Status (as of last session)

The repository is a local MCP gateway PoC plus a web-managed backends UI
in progress. The change proposals below are in flight.

**Recent git history (last few commits):**
```
14ae697 feat(openspec): add task group 9 — production deploy files
510c414 refactor(openspec): swap ESLint+Prettier for Biome, bump router to v8
db99050 feat(openspec): add change proposal for web-managed backends
5139fee docs(arch): add mcp-gateway architecture diagram
ea686ac chore(makefile): switch typecheck target from mypy to ty
01d0b7e feat(observability): add metrics module with counters and Prometheus exposition
4a0d607 fix(backend/sse): migrate to streamable_http transport and bypass system proxy
f30ada5 style: apply ruff format and fix lint issues across codebase
44a9ba7 chore: replace mypy with ty, document quality gates in AGENTS.md
```

**Quality gates (current):** `make format` `make lint` `make typecheck`
`make test` all green. 92 tests passing, ruff 0.16.6, ty 0.0.80, Python
3.13.

**In-flight OpenSpec change:** `openspec/changes/add-web-managed-backends/`
(apply-ready). Replaces YAML-based backend config with a web-managed
store. Highlights:

- `/web/` (Node SPA, **React 19** + Vite + TS + TanStack Query +
  react-router-dom@8 + **Biome** lint/format)
- `packages/web-api/` (Python: FastAPI + SQLAlchemy 2.x async + Alembic
  + asyncpg; serves `/admin/` and `/api/*`)
- `docker-compose.yml` at repo root: **postgres + web-api + gateway in
  one file**, plus per-service Dockerfiles (task group 9)
- Gateway gains `POST /admin/reload` (loopback-only) and a
  `ConfigBackend` selector (`yaml` default | `web` opt-in)
- YAML remains default — existing 92 tests stay green without Postgres

Run `openspec status --change add-web-managed-backends` to see current
artifact state. Apply with `/opsx-apply`.

## 1. Quality Gates (must pass before merge)

All of the following **must succeed locally** before a change is considered done:

| Gate | Command | Purpose |
| --- | --- | --- |
| Format | `make format` | Apply `ruff format` + auto-fixable lint |
| Lint | `make lint` | `ruff check` (E/F/W/I/B/UP) |
| Types | `make typecheck` | `ty check` strict mode |
| Tests | `make test` | 92 pytest tests, all green |
| Coverage | `make test-cov` | ≥ 80% overall, ≥ 90% on `core/` and `config/` |

If any gate fails, **fix the code, not the gate**. Do not add ignores, pragma comments, or `noqa` to silence failures unless explicitly approved.

Once the workspace grows (e.g. `packages/web` is added), the Makefile must provide **per-package** variants — `make test-gateway`, `make lint-web`, etc. — so each member can be iterated on independently. The `make test` / `make lint` umbrella targets should iterate over all members and fail fast on the first broken one.

## 2. Code Style — Google Python Style Guide

We follow the [Google Python Style Guide](https://google.github.io/styleguide/pyguide.html) with these project-specific additions:

### 2.1 Docstrings (Google format)

Every module, class, and **public** function/method must have a docstring.

```python
def list_tools(self) -> list[mcp_types.Tool]:
    """Return the tools exposed by this backend.

    Returns:
        list[mcp_types.Tool]: The tool catalog in the order returned by
            the backend.
    """
```

- Use **section headers** in this order: `Args:`, `Returns:`, `Raises:`, `Yields:`, `Examples:`, `Note:`.
- Keep summaries on **one line** ending with a period.
- No docstrings on private helpers (`_foo`) unless the logic is non-obvious.

### 2.2 Imports

- Use **absolute imports** for first-party (`from mcp_gateway.config import ...`) and **relative** only inside the same package (`from .connection import ...`).
- **Sort** with `ruff` (`I` rule). Order: stdlib → third-party → first-party → relative.
- Avoid wildcard imports (`from x import *`).
- Use `from typing import Any, Callable` for typing constructs; prefer `collections.abc` for runtime ABCs (`Awaitable`, `Iterable`).

### 2.3 Naming

| Element | Convention | Example |
| --- | --- | --- |
| Modules / functions / variables | `snake_case` | `config_loader`, `request_id` |
| Classes / exceptions | `PascalCase` | `GatewayConfig`, `BackendStartupError` |
| Constants | `UPPER_SNAKE_CASE` | `MCP_DEFAULT_TIMEOUT` |
| Private members | `_leading_underscore` | `_session_cm` |
| Type variables | `PascalCase` (short) | `T`, `R` |
| Enum members | `UPPER_SNAKE_CASE` | `BackendState.HEALTHY` |

### 2.4 Line length, formatting, type hints

- **Line length**: 100 (configured in `[tool.ruff]`).
- **Target version**: Python 3.13 (`target-version = "py313"`).
- Always use `from __future__ import annotations` in every source file.
- Prefer built-in generics: `list[str]`, `dict[str, int]`, `tuple[int, ...]` (PEP 585).
- Use `X | None` for optional types (PEP 604).
- Avoid `Any` where a concrete type is possible; if unavoidable, annotate it.
- Prefer `dataclass(frozen=True)` over manual `__init__` / `__eq__`.

### 2.5 Error handling

- Raise specific exception types; never `raise Exception(...)`.
- Custom exceptions subclass a standard hierarchy (`RuntimeError`, `ValueError`).
- Log errors with `structlog` using `event=snake_case` and structured kwargs:

```python
logger.error("backend_start_failed", backend=name, error=str(exc))
```

- **Do not** log and re-raise the same exception unless adding context — use `raise NewError(...) from exc`.

### 2.6 Concurrency

- All async code uses `async def` / `await`; no blocking calls inside event loops.
- Cancel and clean up resources on shutdown (`asyncio.timeout`, context managers).
- Never share mutable state between tasks without a lock.

### 2.7 Logging

- Use `from ..observability import get_logger`; never `logging.getLogger`.
- Log messages are **events** (`backend_connected`), not sentences.
- Always pass structured kwargs, never f-strings.

## 3. Tooling — Single Source of Truth

All tooling versions and rules are pinned in `pyproject.toml`. **Do not introduce additional linters/formatters** without updating this file.

### 3.1 `ruff` (formatter + linter)

- **Form** + **import-sort** are enforced by `ruff format src tests` and `ruff check --fix src tests`.
- Selected rule sets (`[tool.ruff.lint]`):
  - `E`/`W` — pycodestyle errors/warnings
  - `F` — pyflakes (undefined names, unused imports)
  - `I` — isort import order
  - `B` — bugbear (common pitfalls)
  - `UP` — pyupgrade (modern syntax)
- **Ignored**: `E501` (line length handled by formatter).
- Run on every PR: `make lint` and `make format`.

### 3.2 `ty` (type checker)

- Astral's `ty` is the project's strict type checker (`make typecheck`).
- All `src/` must type-check **without errors**. Warnings are acceptable but should be addressed.
- Use `# ty: ignore[rule-code]` (not `# type: ignore`) for documented exceptions; add a comment explaining why.
- Avoid `# mypy:` and `# pyright:` comments — they are dead noise under `ty`.

### 3.3 `pytest` (test runner)

- Tests live under `tests/` mirroring `src/mcp_gateway/`.
- Naming: `test_<unit>.py` for unit, `test_<feature>_integration.py` for integration, `test_<flow>.py` under `tests/e2e/` for end-to-end.
- All async tests run with `asyncio_mode = "auto"`.
- Mock external MCP servers via fixtures in `tests/fixtures/`.
- Aim for **deterministic** tests — no real network, no real clock.

### 3.4 `uv` (package manager)

- All dependency changes go through `pyproject.toml` then `uv pip install -e ".[dev]"`.
- Never commit a `requirements.txt`; the lock state lives in the venv.

## 4. Required Pre-Commit Workflow

Before committing or opening a PR, run the full quality loop:

```sh
make format    # auto-fix formatting + lint
make lint      # verify zero diagnostics
make typecheck # verify ty passes
make test      # 92 tests pass
```

All four must succeed. CI should re-run the same commands on Linux.

## 5. Adding a New Tool / Rule

1. Propose the addition in an issue or PR description.
2. Update `pyproject.toml` configuration.
3. Update `make lint` / `make typecheck` targets if needed.
4. Update this file (`AGENTS.md`) under the matching section.
5. Run the full quality loop to confirm zero regressions.

## 6. Agent-Specific Rules

When an AI agent (e.g. opencode, Claude Code, Codex) edits this repo:

- **Never** disable a lint or type rule without a one-line justification comment.
- **Never** add `print(...)` for debugging — use `logger.debug("event", **kwargs)`.
- **Never** rewrite `pyproject.toml` dependency versions downward.
- **Never** create files outside `src/mcp_gateway/`, `tests/`, `examples/`, or `docs/` without explicit instruction.
- **Always** run the full quality loop after edits; do not declare a task complete on partial checks.
- **Always** keep the existing file's structure: imports sorted, `from __future__ import annotations` first, Google-style docstrings.
- **Always** update or add tests when behavior changes.

## 7. Project Layout

This repository is a **uv workspace** that hosts one or more independently installable Python packages. Today there is one member (`packages/mcp-gateway`); the structure below is designed so a second project (e.g. `packages/web`) can be added without restructuring the gateway or duplicating tooling.

### 7.1 Monorepo directory tree

```
mcp-gateway-poc/                          # workspace root
├── packages/                             # workspace members (uv workspaces)
│   ├── mcp-gateway/                      # gateway package
│   │   ├── pyproject.toml                # package-level deps + tooling overrides
│   │   ├── README.md
│   │   ├── src/mcp_gateway/              # installable package (src-layout)
│   │   │   ├── __init__.py               # public re-exports
│   │   │   ├── cli.py                    # CLI entry point (mcp-gateway script)
│   │   │   ├── backend/                  # backend connection adapters
│   │   │   ├── config/                   # YAML config + hot reload
│   │   │   ├── core/                     # domain logic, no I/O knowledge
│   │   │   ├── frontend/                 # FastAPI HTTP/SSE layer
│   │   │   └── observability/            # logging, request-id, metrics
│   │   ├── tests/                        # mirrors src/ (test_<module>.py)
│   │   │   ├── unit/
│   │   │   ├── integration/
│   │   │   ├── e2e/
│   │   │   └── fixtures/                 # mock MCP servers (stdio + HTTP/SSE)
│   │   └── examples/                     # runnable demos + sample configs
│   │       ├── mcp-gateway.yaml
│   │       └── mock_backend.py
│   └── web/                              # future web package (placeholder)
│       └── pyproject.toml
├── docs/                                 # cross-package documentation
├── openspec/                             # spec-driven change proposals
├── pyproject.toml                        # workspace root: shared tooling config
├── uv.lock                               # uv lockfile (committed)
├── Makefile                              # workspace-level task runner
├── README.md
└── AGENTS.md                             # this file
```

### 7.2 uv workspace setup

The workspace root declares members and shared dev tooling; each package owns its own runtime deps.

**Root `pyproject.toml`:**

```toml
[project]
name = "mcp-gateway-poc-workspace"
version = "0.0.0"
requires-python = ">=3.13"

[tool.uv.workspace]
members = ["packages/*"]

[tool.uv]
dev-dependencies = [
    "ruff>=0.12.0",
    "ty",
    "pytest>=8.3.0",
    "pytest-asyncio>=0.24.0",
    "pytest-cov>=5.0.0",
]

[tool.ruff]
line-length = 100
target-version = "py313"

[tool.ruff.lint]
select = ["E", "F", "W", "I", "B", "UP"]
ignore = ["E501"]

[tool.ty.src]
include = ["packages/*/src"]

[tool.ty.environment]
python-version = "3.13"
```

**Per-package `pyproject.toml` (only runtime deps + package metadata):**

```toml
[project]
name = "mcp-gateway"
version = "0.1.0"
requires-python = ">=3.13"
dependencies = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.32.0",
    # ... gateway-specific runtime deps only
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/mcp_gateway"]
```

Key rules:

- The workspace root **never** lists runtime deps for any member — only shared dev tooling.
- Each member `pyproject.toml` is the source of truth for that package's runtime deps.
- `uv.lock` lives at the workspace root and is committed; per-member venvs come from `uv sync`.

### 7.3 Layering rules (enforced by review)

Dependencies only flow **downward** within a single package:

```
cli  →  frontend  →  core  →  backend  →  (mcp SDK, httpx2)
                       ↘   config
                       ↘   observability
```

- `core/` **must not** import from `frontend/`, `cli/`, or `backend/`. It only defines domain types and the registry/router.
- `backend/` may import from `core/` (for the `BackendConnection` protocol) and `config/` (for typed config models).
- `frontend/` may import from `core/`, `config/`, `backend/` types — never instantiate adapters directly; ask `BackendConnectionManager`.
- `observability/` is a leaf module: it may be imported by anyone, imports nothing from the project.
- Cross-cutting concerns (logging, request-id, http client, metrics) live in `observability/` so they can be swapped without touching domain code.

**Cross-package rules:**

- Package A may import from package B only if B is declared as a runtime dependency in A's `pyproject.toml`.
- Cross-package imports use **absolute** paths: `from mcp_gateway.observability import get_logger`, never `from ..observability`.
- Shared interfaces (e.g. logging, metrics, request-id context) belong in the **most-depended-on** package; promote, don't duplicate.

### 7.4 `__init__.py` discipline

Every package has an `__init__.py` that **re-exports the public API**:

```python
# packages/mcp-gateway/src/mcp_gateway/backend/__init__.py
from .connection import BackendConnection, BackendState, BackendStatus
from .fake import FakeBackendConnection
from .http_sse import HttpSseBackend
from .stdio import StdioBackend, BackendStartupError

__all__ = [
    "BackendConnection",
    "BackendState",
    "BackendStatus",
    "BackendStartupError",
    "FakeBackendConnection",
    "HttpSseBackend",
    "StdioBackend",
]
```

- Importers write `from mcp_gateway.backend import StdioBackend`, never `from mcp_gateway.backend.stdio import StdioBackend`.
- `__all__` is **mandatory** and must list every public name. `ruff` will flag missing entries.
- Keep `__init__.py` files thin — no logic, no side effects beyond re-exports.

### 7.5 Module file template

Every new `.py` file under `packages/*/src/` starts with:

```python
"""One-line module description ending with a period.

Longer explanation if the module's purpose is non-obvious. Keep it under
five lines; longer docs belong in `docs/`.
"""

from __future__ import annotations

# stdlib
# third-party
# first-party (mcp_gateway.*)
# relative (same package)

__all__ = ["PublicName", ...]
```

## 8. Adding a New Module / Package

Follow this checklist whenever you introduce a new file, class, sub-package, or workspace member. It mirrors the pre-commit loop in §4.

### 8.1 Decision tree — where does it go?

**Inside an existing package (e.g. `packages/mcp-gateway/`):**

| You're adding… | Put it in… |
| --- | --- |
| Domain type or algorithm with no I/O | `packages/<pkg>/src/<pkg>/core/` |
| New MCP backend transport (e.g. WebSocket) | `packages/<pkg>/src/<pkg>/backend/<transport>.py` + update `backend/__init__.py` |
| HTTP endpoint / FastAPI route | `packages/<pkg>/src/<pkg>/frontend/` |
| Pydantic config model | `packages/<pkg>/src/<pkg>/config/` |
| Logger / tracing / metrics helper | `packages/<pkg>/src/<pkg>/observability/` |
| Standalone script for humans | `packages/<pkg>/examples/` (not `src/`) |
| Shared mock used by tests | `packages/<pkg>/tests/fixtures/` |
| Pure unit test | `packages/<pkg>/tests/unit/test_<module>.py` |
| Cross-module test | `packages/<pkg>/tests/integration/test_<feature>_integration.py` |
| Test that spawns subprocesses | `packages/<pkg>/tests/e2e/test_<flow>.py` |

**Adding a brand-new workspace member (e.g. `packages/web/`):**

| Step | Action |
| --- | --- |
| 1 | Create `packages/web/` with its own `pyproject.toml`, `src/web/`, `tests/`, `README.md` |
| 2 | Add `dependencies` (runtime) only — never to the workspace root |
| 3 | Re-export public API from `src/web/__init__.py` (see §7.4) |
| 4 | The workspace root already discovers it via `members = ["packages/*"]` — no edit needed |
| 5 | Add a `make test-web` / `make lint-web` target so it can run in isolation |
| 6 | If `web` consumes `mcp-gateway`, add `mcp-gateway` to `web`'s runtime `dependencies` |

### 8.2 Step-by-step recipe (new file inside an existing package)

1. **Create the file** under the right directory using the template from §7.5.
2. **Implement the public API** with full type hints and Google-style docstrings (§2.1, §2.4).
3. **Re-export** any new public names from the package's `__init__.py` and append them to `__all__`.
4. **Register the entry point** if the module plugs into an existing registry (e.g. a new transport type must be added to the factory in `core/manager.py` and the literal-union in `config/__init__.py`).
5. **Write tests** in `tests/`:
   - Unit tests for pure logic (no fixtures, no I/O).
   - Integration tests if the module crosses a layer boundary.
   - Update or add an E2E fixture if it talks to an external MCP server.
6. **Run the full quality loop** — see §4. All four gates must pass.
7. **Update this file** (`AGENTS.md`) if the new module changes layering, tooling, or workflow rules.
8. **Open a PR** with: summary, linked issue, the quality-loop output pasted in the description.

### 8.3 Adding a new backend transport (worked example)

Say you want to add a WebSocket backend to `mcp-gateway`:

1. Create `packages/mcp-gateway/src/mcp_gateway/backend/websocket.py` with class `WebSocketBackend(BackendConnection)`.
2. Add `WebSocketBackend` to `packages/mcp-gateway/src/mcp_gateway/backend/__init__.py` and `__all__`.
3. Add `"websocket"` to the `transport` literal in `config/__init__.py:BackendConfig` discriminated union.
4. Add the factory branch in `core/manager.py:BackendConnectionManager._create_backend`.
5. Add the new transport's required fields (URL, headers, …) to `BackendConfig` in `config/__init__.py`.
6. Write `packages/mcp-gateway/tests/unit/test_websocket_backend.py` using `FakeBackendConnection`-style patterns.
7. If you have a real WS server for testing, add it under `packages/mcp-gateway/tests/fixtures/ws_mock_server.py` and an E2E test.
8. Run `make format && make lint && make typecheck && make test`. Fix anything that breaks.
9. Update `packages/mcp-gateway/README.md` "Configuration" and `packages/mcp-gateway/examples/mcp-gateway.yaml` to show the new transport.

### 8.4 Deprecating or removing a module

- Never delete a module in the same PR that introduces its replacement.
- Mark it deprecated with a module-level warning + `DeprecationWarning` at first import.
- Keep it for at least one minor release; document removal in `CHANGELOG.md`.
- After removal, delete its tests and any references in `__init__.py`, `__all__`, docs, and examples.

### 8.5 Promoting code across packages

When a helper used by multiple packages graduates from "single-package internal" to "shared":

1. Pick the most-depended-on package as the canonical home (typically `mcp-gateway` for shared observability primitives in the early days).
2. Move the module preserving its history (`git mv`); do not re-create it.
3. Update the destination's `__init__.py` re-export and `__all__`.
4. Add a runtime dep in every consuming package's `pyproject.toml`.
5. Replace any duplicated copies in other packages with imports from the canonical home.
6. Update layering diagrams in `AGENTS.md` if the move changes the dependency graph.