# ADR-015: Job Description and Resume Matching

## Status

Accepted

## Context

Generic interview questions do not reflect a candidate's target role. The product needs a deterministic way to identify job requirements, compare them with resume evidence and focus the interview on gaps.

## Decision

Use a catalog-backed matching pipeline:

- normalize text and match canonical skills through aliases;
- use word boundaries for ASCII aliases to avoid false positives;
- require a meaningful JD with at least one supported skill;
- compute matched, missing and bonus skills;
- generate risk areas and suggested interview focus;
- pass the match summary into question prompts;
- expose the same pure matcher through FastAPI.

The matcher does not call an LLM and is fully testable offline.

## Consequences

Positive:

- interviews target a real role rather than a generic question bank;
- matching is explainable and reproducible;
- API clients and the UI share one algorithm;
- missing skills become input to the existing deterministic workflow.

Negative:

- the initial catalog is technology-focused;
- alias coverage requires maintenance;
- keyword matching cannot understand every equivalent skill or achievement.

## Follow-up

Expand the skill catalog by job family and add reviewed semantic aliases where deterministic matching is insufficient.
