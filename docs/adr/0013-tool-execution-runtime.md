# ADR-013: Tool Execution Runtime

## Status

Accepted

## Context

The ToolRegistry previously exposed metadata and called handlers directly. That was enough for local composition, but it lacked the controls expected from an agent platform: timeouts, safe retries, duplicate-request handling, and an audit trail tied to an AgentRun.

## Decision

Add an execution policy to every `ToolSpec`:

- timeout;
- retry count;
- idempotency capability;
- idempotency TTL;
- required permission.

The runtime provides:

- permission checks before any handler execution;
- timeout isolation using a daemon worker thread;
- retries only when the tool is explicitly marked idempotent;
- a process-local idempotency cache keyed by tenant, tool, and idempotency key;
- input-digest comparison so one key cannot be reused with different arguments;
- audit events for start, retry, completion, cache hit, timeout, failure, denial, and idempotency conflict;
- an authenticated API endpoint that records tool events on the owning AgentRun.

Bytes outputs are returned as base64 metadata, and Path outputs are converted to strings so the API response remains JSON-compatible.

## Consequences

Positive:

- unsafe side-effecting tools cannot be retried accidentally;
- duplicate requests can be detected and replayed safely within one process;
- tool calls become visible in the same trace as model and interview events;
- permission and tenant context are carried into every audit event;
- execution policy is testable without network services.

Negative:

- Python threads cannot forcibly stop a stuck handler;
- the idempotency cache is process-local and is lost on restart;
- multi-worker deployments need a shared cache or database-backed idempotency store;
- input schemas and output schemas are not yet enforced;
- arbitrary third-party tools still require process isolation or sandboxing.

## Follow-up

Move idempotency to Redis or PostgreSQL, add input/output schema validation, run untrusted tools in isolated workers, add queue-backed execution and distributed cancellation, and expose tool-level latency and failure metrics.
