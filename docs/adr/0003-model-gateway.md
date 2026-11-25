# ADR-003: Route Model Calls Through a Model Gateway

## Status

Accepted

## Decision

All model calls go through `ModelGateway` with task-specific profiles:

- `question`;
- `tagging`;
- `review`.

The gateway returns content plus task, model, prompt version, latency, and estimated token counts.

## Context

Direct provider calls inside business logic make it difficult to:

- change models;
- add fallback providers;
- measure cost;
- version prompts;
- test business logic without network calls.

## Consequences

Positive:

- model routing can evolve independently;
- each call carries observability metadata;
- business modules depend on a stable interface.

Negative:

- one more abstraction layer to maintain;
- current implementation still uses a single provider.

## Follow-up

Add provider fallback, budget limits, circuit breakers, and per-tenant model quotas.
