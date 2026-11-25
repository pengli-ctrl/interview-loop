# ADR-005: Tenant Isolation, PII, and Tool Permissions

## Status

Proposed for public beta

## Context

Resume text, audio, interview answers, and feedback are sensitive personal data. Future tools may access storage, model providers, and exports. A public platform cannot rely on shared local files or unrestricted tool calls.

## Decision

Every future AgentRun must carry:

- `tenant_id`;
- `user_id`;
- trace ID;
- data-retention policy.

Tool specifications must declare:

- required permission;
- input and output schema;
- timeout;
- retry policy;
- audit behavior.

## Required Controls

- tenant-scoped database queries;
- object-storage prefixes by tenant;
- PII redaction before analytics;
- explicit recording consent;
- data export and deletion;
- audit logs for human access;
- tool permission checks.

## Consequences

Public deployment is blocked until these controls exist. The current local MVP remains suitable for invited, non-production testing only.


## Implementation Status

The single-process slice now carries trace ID and retention metadata, requires explicit consent, redacts common PII from trace payloads, scopes local paths by tenant, supports export and deletion, validates tool input/output schemas, and persists audit events in SQLite. Centralized identity, durable centralized audit storage, and legal retention operations remain production follow-ups.
