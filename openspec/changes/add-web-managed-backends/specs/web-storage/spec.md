## ADDED Requirements

### Requirement: Backends are persisted in PostgreSQL

The web package SHALL persist the backend set in a PostgreSQL database accessed via SQLAlchemy 2.x with the `asyncpg` driver. Each backend SHALL be a row in a `backends` table with columns that mirror the YAML schema: `id` (UUID), `name` (unique, slug), `transport` (`stdio` | `sse`), `command` (nullable), `args` (JSONB), `env` (JSONB), `url` (nullable), `headers` (JSONB), `startup_timeout_s` (float), `created_at`, `updated_at`.

#### Scenario: A created backend is stored

- **WHEN** the web UI creates a new backend and the request commits successfully
- **THEN** a row exists in the `backends` table with the submitted fields and a server-generated `created_at`

#### Scenario: An edit updates the row in place

- **WHEN** the web UI edits a backend and the request commits successfully
- **THEN** the same row's columns reflect the new values and `updated_at` advances

#### Scenario: A delete removes the row

- **WHEN** the web UI deletes a backend and the request commits successfully
- **THEN** no row with that `id` exists in `backends` after the commit

### Requirement: Schema migrations are managed by Alembic

The web package SHALL ship an Alembic configuration under `packages/web-api/alembic/` so that the schema is created and migrated by an explicit command (`alembic upgrade head`), not by auto-creating tables on startup. The initial migration SHALL create the `backends` table described above.

#### Scenario: Fresh database is brought to head

- **WHEN** `alembic upgrade head` is run against an empty PostgreSQL database
- **THEN** the `backends` table exists with the documented columns and indexes (unique on `name`)

#### Scenario: Startup does not auto-create the schema

- **WHEN** the web service starts against an empty database without `alembic upgrade head` having been run
- **THEN** startup fails with a clear "schema not migrated" error pointing the operator at the migration command

### Requirement: Local Postgres runs via docker-compose

A `docker-compose.yml` at the repository root SHALL define a `postgres` service for local development, using a named volume for persistence and exposing port 5432 on `127.0.0.1`. The compose file SHALL target OrbStack-compatible defaults but run on any Docker host.

#### Scenario: `docker compose up -d postgres` starts the service

- **WHEN** the operator runs `docker compose up -d postgres` from the repo root with OrbStack (or Docker Desktop) running
- **THEN** a `postgres` container is running, listening on `127.0.0.1:5432`, with the configured credentials and database name

#### Scenario: Data survives a container restart

- **WHEN** the operator stops and restarts the `postgres` container
- **THEN** rows previously inserted into `backends` are still present after the restart

#### Scenario: Default credentials are documented in `.env.example`

- **WHEN** a new operator clones the repo
- **THEN** `.env.example` at the repo root documents `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, and the web package's `DATABASE_URL` so they can copy it to `.env`