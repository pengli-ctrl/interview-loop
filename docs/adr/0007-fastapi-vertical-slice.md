# ADR-007: FastAPI Vertical Slice with In-Memory Repository

## Status

Accepted

## Context

The Streamlit MVP is sufficient for UI validation, but an Agent platform needs a service boundary that can later support web clients, workers, mobile apps, and enterprise integrations.

A full PostgreSQL and distributed-service implementation would slow iteration at this stage.

## Decision

Add a FastAPI vertical slice with:

- `/health`;
- `/v1/tools`;
- AgentRun creation and retrieval;
- AgentRun start and event append endpoints;
- shared ToolRegistry metadata;
- an in-memory repository for local development and tests.

## Consequences

Positive:

- API contract and OpenAPI documentation exist early;
- Streamlit and future clients can share platform primitives;
- authentication, persistence, and worker integration have a clear seam.

Negative:

- in-memory runs are lost on restart;
- no tenant authorization yet;
- no production-grade concurrency control.

## Follow-up

Replace the in-memory repository with PostgreSQL, add authentication and tenant authorization, then move long-running execution into queue-backed workers.
