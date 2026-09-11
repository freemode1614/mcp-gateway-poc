## ADDED Requirements

### Requirement: New endpoints emit access logs with request_id

The gateway's `RequestIDMiddleware` SHALL cover every new HTTP route added to the gateway surface (currently `POST /admin/reload`) so that each request appears in the structured JSON access log with a `request_id`, `method`, `path`, and `status` field, matching the existing log shape used by `/messages`, `/sse`, and `/health`.

#### Scenario: Admin reload appears in access logs

- **WHEN** a successful `POST /admin/reload` completes
- **THEN** exactly one access log line is emitted with `request_id`, `method="POST"`, `path="/admin/reload"`, and `status=200`

#### Scenario: Rejected admin reload is logged

- **WHEN** a `POST /admin/reload` is rejected with `403` because the source is non-loopback
- **THEN** the access log line shows `status=403` and the `request_id` matches the `X-Request-Id` header (if any) or a server-generated ID