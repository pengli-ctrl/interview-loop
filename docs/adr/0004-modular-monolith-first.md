# ADR-004: Modular Monolith Before Microservices

## Status

Accepted

## Context

The platform currently has one deployable Streamlit client and a small set of domain services. Introducing microservices, service discovery, distributed tracing, and independent databases at this stage would add operational cost without immediate product value.

## Decision

Keep one deployable application while enforcing module boundaries:

- `core` for pure business logic;
- `services` for external integrations;
- `rag` for retrieval;
- `storage` for persistence;
- `export` for records;
- `platform` for AgentRun, tools, and model gateway.

## Consequences

Positive:

- faster iteration;
- simpler local development and testing;
- lower infrastructure cost;
- clear seams for future extraction.

Negative:

- shared process resources;
- limited independent scaling;
- eventual API and worker split will be required.

## Follow-up

Extract FastAPI, workers, PostgreSQL, Redis, and object storage when public beta traffic justifies the operational complexity.
