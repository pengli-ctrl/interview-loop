# ADR-008: SQLite-First Persistence for the API Slice

## Status

Accepted

## Context

ADR-007 used an in-memory repository. That made runs disappear on service restart and prevented verification of persistence behavior.

A full PostgreSQL deployment is still premature for the current architecture phase.

## Decision

Use SQLite as the default development repository behind the `AgentRunRepository` interface.

The repository persists:

- AgentRun metadata and status;
- event timeline;
- tenant_id;
- current node and timestamps.

Tests use temporary SQLite databases, verifying real persistence without external infrastructure.

## Consequences

Positive:

- AgentRuns survive API restarts;
- repository behavior can be tested locally and in CI;
- the same interface can later be implemented with PostgreSQL.

Negative:

- SQLite is not suitable for multi-writer production scale;
- no row-level tenant authorization yet;
- no migration framework yet.

## Follow-up

Implement PostgreSQL using the same repository protocol, add migration tooling, tenant authorization, and event streaming.
