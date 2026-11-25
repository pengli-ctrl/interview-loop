# ADR-010: SSE Event Streaming for Agent Runs

## Status

Accepted

## Context

Clients need progress updates while an interview AgentRun is executing. Polling every endpoint can increase load and create inconsistent state views.

## Decision

Expose a Server-Sent Events endpoint:

`GET /v1/agent-runs/{run_id}/events/stream`

The endpoint:

- replays existing events from the persisted Run;
- polls for new events;
- emits keep-alive comments;
- closes when the Run is completed or failed;
- enforces tenant scope and API key authentication.

## Consequences

Positive:

- simple browser-native streaming;
- works through the existing HTTP API;
- provider-independent contract.

Negative:

- current implementation polls SQLite once per second;
- horizontal scaling would duplicate or miss events without a shared broker;
- future workers need Redis Streams or a message queue.

## Follow-up

Move event fan-out to Redis Streams or a queue-backed event bus when the API is scaled beyond one process.
