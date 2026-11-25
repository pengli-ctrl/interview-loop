# ADR-001: Use a Deterministic Interview Workflow

## Status

Accepted

## Context

Technical interviews have a known structure: self-introduction, project overview, deep dive, technical questions, system design, and candidate questions. A fully autonomous agent could dynamically choose any topic, but that creates risks:

- stage skipping or repeated questions;
- unstable interview duration;
- poor auditability;
- hard regression testing;
- unpredictable cost.

## Decision

Use a deterministic workflow and state machine for the interview skeleton. LLM generation is constrained to the current stage, current main question, and configured follow-up budget.

## Consequences

Positive:

- predictable stage transitions;
- testable behavior;
- easier cost and time control;
- clear traceability.

Negative:

- less open-ended than an autonomous planner;
- new stages require explicit configuration.

## Notes

Autonomy can be added later inside a bounded node, but the outer interview lifecycle should remain deterministic.
