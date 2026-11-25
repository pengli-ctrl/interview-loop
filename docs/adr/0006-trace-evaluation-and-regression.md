# ADR-006: Trace, Evaluation, and Regression

## Status

Accepted as initial platform direction

## Context

LLM products fail in ways that unit tests alone cannot capture: retrieval misses, prompt regressions, model changes, malformed output, increased latency, and cost drift.

## Decision

Introduce a platform-level trace and evaluation model.

## AgentRun Events

Record:

- stage transitions;
- question generation;
- tool calls;
- model calls;
- answer ingestion;
- evaluation;
- record export;
- errors and retries.

## Evaluation Layers

1. Pure logic tests.
2. Prompt and parser tests.
3. RAG golden dataset.
4. Model output rubric checks.
5. Human review and score calibration.
6. Trace replay for regressions.

## Metrics

- retrieval Recall@K and MRR;
- question stage adherence;
- duplicate question rate;
- follow-up relevance;
- report actionability;
- latency P50/P95;
- token and estimated cost per run;
- failure and retry rate.

## Consequences

The project becomes more than a prompt demo: it gains a path to measurable, comparable and governable Agent behavior.
