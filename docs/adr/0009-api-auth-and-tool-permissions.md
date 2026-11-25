# ADR-009: API Authentication, Tenant Scoping, and Tool Permissions

## Status

Accepted

## Context

Run records and future tool executions contain sensitive interview data. A service API without authentication or tenant scoping would allow cross-user access and uncontrolled tool use.

## Decision

1. Optional API key authentication through `INTERVIEWLOOP_API_KEY`.
2. Principal resolved from:
   - `X-API-Key`;
   - `X-Tenant-Id`;
   - `X-User-Id`;
   - `X-Permissions`.
3. Every Run lookup and mutation is tenant-scoped.
4. ToolRegistry checks `required_permission` before executing a tool.

## Consequences

Positive:

- cross-tenant run access is blocked;
- tool permissions become explicit;
- the API has a clear security seam for JWT/OIDC.

Negative:

- header-based identity is not sufficient for production;
- permission strings are not yet managed by an identity provider;
- local development defaults remain permissive when no API key is configured.

## Follow-up

Adopt OIDC/JWT or enterprise SSO and centralize RBAC/ABAC policies. Tool execution audit logging is implemented in ADR-013; production still needs durable centralized audit storage and retention controls.
