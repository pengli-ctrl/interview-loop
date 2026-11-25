# ADR-012: Model Routing, Budgets and Telemetry

## Status

Accepted

## Context

InterviewLoop originally used one model provider for every task. A transient provider error could stop an interview, and the application had no shared view of token usage or estimated cost. The first question was also generated before the AgentRun existed, so it was missing from the execution trace.

## Decision

Use ordered, task-specific model profiles behind `ModelGateway`:

- each profile has a provider, model name, prompt version, retry count and per-million-token prices;
- retries happen within a profile, then the gateway advances to the next profile;
- empty responses and provider exceptions are treated as failures;
- each AgentRun owns an independent `UsageBudget`;
- budget utilization and estimated cost are recorded on every `model.call` event;
- the interview record stores a `model_usage` summary;
- the UI exposes current usage and the most recent model calls.

The cost values are estimates based on configurable unit prices, not provider invoices. A post-call overrun is charged to the budget and blocks subsequent calls.

## Consequences

Positive:

- one provider failure no longer immediately breaks the workflow;
- model choice and prompt versions are observable per task;
- a single interview cannot silently consume an unbounded model budget;
- traces now include the first question and the usage context of later calls;
- the same gateway can be reused by the API and future agent workers.

Negative:

- a single response can still cross the budget because provider output length is not known before the call;
- retries increase latency and cost;
- provider prices must be maintained when vendors change pricing;
- the current implementation does not yet include circuit breakers or health-aware routing.

## Follow-up

Add provider health tracking, circuit breakers, maximum output-token reservation, per-tenant quotas, and provider-invoice reconciliation.
