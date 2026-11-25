# ADR-016: Structured Report and Growth Loop

## Status

Accepted

## Context

A free-form review is difficult to compare across sessions. Candidates need explicit scores, evidence and a next action, while the platform needs structured history for trends and regression.

## Decision

Build a deterministic report layer from the existing interview messages and scenario Rubric:

- weighted dimension scores;
- overall score;
- evidence excerpt for each dimension;
- strengths and risks;
- prioritized action plan;
- job-match gaps included in risks and actions;
- cross-session progress records and weak-area changes.

The report is stored in session JSON and rendered in Markdown. Old sessions without structured reports remain readable and show a compatibility notice.

## Consequences

Positive:

- every interview produces comparable structured data;
- reports connect evidence to recommendations;
- growth trends work without another model call;
- demo and tests are deterministic.

Negative:

- heuristic scores are less semantically accurate than a calibrated LLM evaluator;
- the current score uses answer structure and keyword signals;
- real human calibration remains necessary before high-stakes use.

## Follow-up

Calibrate the deterministic baseline against larger human-reviewed datasets and optionally blend structured LLM scores when confidence is high.
