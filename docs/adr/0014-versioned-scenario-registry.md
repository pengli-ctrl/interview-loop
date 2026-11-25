# ADR-014: Versioned Scenario Registry

## Status

Accepted

## Context

Interview rounds, stages, question plans and timing were embedded directly in `config.py`. Adding a new role or interview format would require code changes and duplicate state-machine logic.

## Decision

Use versioned JSON scenario packs plus a typed registry:

- `ScenarioPack` declares schema version, job family, role, seniority, language and styles;
- `ScenarioSpec` declares interview round, duration, tags, stages and Rubric;
- `StageSpec` declares question plans, fallback pool, follow-up limits and time budget;
- validation rejects empty stages/question plans, duplicate identifiers, invalid durations and Rubric weights that do not sum to 1.0;
- Streamlit and FastAPI load the same `ScenarioRegistry`;
- the previous `MODE_CONFIG` shape is generated as a compatibility adapter.

## Consequences

Positive:

- new scenarios become content changes rather than branching application code;
- stage timing and scoring dimensions are explicit;
- API clients and the UI use one source of truth;
- scenario packs can be versioned and reviewed.

Negative:

- invalid packs fail at startup instead of silently degrading;
- schema migration is required when model fields change;
- content authoring still needs an admin editor.

## Follow-up

Add scenario authoring and validation UI in the control-plane phase.
