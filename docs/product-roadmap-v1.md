# InterviewLoop Product Roadmap v1

Baseline: `v0.10.0`

This roadmap moves the project from an architecture-heavy prototype to a coherent interview-training product. Each step has a fixed scope and acceptance gate. A later step starts only after the previous step passes.

## Product direction

Position InterviewLoop as an AI interview-training platform:

- first wedge: technical interviews;
- expansion: general professional, product, data, operations and campus interviews;
- loop: target context -> interview -> evidence-based report -> training plan -> retraining;
- platform surface: candidate workspace, scenario configuration, minimal control plane.

## Execution status

| Step | Status | Evidence |
|---|---|---|
| 1. Product shell and information architecture | Complete | Five views, three-step setup, native theme, full AppTest flow |
| 2. Scenario model and configuration registry | Not started | Pending Step 1 closure |
| 3. JD and resume matching | Not started | Pending Step 2 |
| 4. Report and growth loop | Not started | Pending Step 3 |
| 5. Minimal platform control plane | Not started | Pending Step 4 |

## Step 1: Product shell and information architecture

### Scope

- Replace the single stacked control page with five product views:
  - dashboard;
  - interview setup wizard;
  - focused interview room;
  - report;
  - growth and history.
- Move model usage and technical diagnostics out of the candidate main flow.
- Add a native Streamlit theme and consistent page branding.
- Use Material icons and reduce emoji-driven visual noise.
- Preserve the existing interview state machine, voice/text answer flow, report export and consent requirements.

### Completion level

A user can understand where to start, complete an interview without seeing unrelated statistics, read the report, and return to history through clear navigation.

### Acceptance criteria

- Dashboard is the default view.
- Sidebar navigation exposes exactly the five primary views.
- Setup uses at least a three-step flow and does not show interview or history controls.
- Interview room shows only stage progress, timer, question and answer controls.
- Report view shows the review, tags, export and next actions.
- Growth view contains weakness statistics, history and optional technical diagnostics.
- Full demo interview still transitions through all stages and generates Markdown/JSON.
- `AppTest` covers navigation and the complete demo flow.
- `ruff check .` and full `pytest -q` pass.

## Step 2: Scenario model and configuration registry

### Scope

- Introduce a typed scenario model:
  - job family;
  - role;
  - seniority;
  - interview round;
  - language;
  - duration;
  - style;
  - stages;
  - main-question plans;
  - follow-up limits;
  - rubric dimensions.
- Move hardcoded modes into versioned configuration files.
- Preserve existing technical rounds through compatibility migration.

### Completion level

The interview engine runs from scenario configuration rather than hardcoded `MODE_CONFIG` dictionaries.

### Acceptance criteria

- Scenario schema validation rejects missing stages, empty question plans and invalid weights.
- All existing technical and HR rounds load from scenario packs with unchanged behavior.
- App and API use the same scenario registry.
- Scenario loading and transition tests pass.
- Existing full-flow AppTest remains green.

## Step 3: JD and resume matching

### Scope

- Let candidates paste a job description and upload or reuse a resume.
- Extract required skills, responsibilities and seniority signals.
- Compute deterministic match/gap results before the interview.
- Feed matched gaps into question generation.
- Show a compact match summary in setup and report.

### Completion level

The product moves from generic mock interviews to interviews targeted at a real role and resume.

### Acceptance criteria

- JD parsing and skill normalization are pure, testable functions.
- Empty, short and malformed JD inputs produce clear validation messages.
- Match report includes matched skills, missing skills, risk areas and suggested focus.
- Interview generation receives JD and gap context.
- Tests cover good, partial and poor matches.
- No real API key is required for the matching tests.

## Step 4: Report and growth loop

### Scope

- Add structured score dimensions and evidence to reports.
- Add score cards, dimension charts, strengths, risks and a concrete next-practice plan.
- Add cross-session trends and weak-skill progression.
- Preserve old session compatibility.

### Completion level

After an interview, the user can see what was strong, what failed, why, and what to practice next.

### Acceptance criteria

- Report shows overall score, dimension scores, evidence excerpts and action plan.
- Growth page shows at least one trend chart and recent weak-area changes.
- Old session files without new scores still load with a safe fallback.
- Report generation is deterministic in demo mode and testable without external services.
- Full interview -> report -> history AppTest passes.

## Step 5: Minimal platform control plane

### Scope

- Add a separate admin view for:
  - scenario packs;
  - model profiles and routing metadata;
  - tool catalog and permissions;
  - tenant quotas;
  - recent AgentRuns and Trace;
  - evaluation metrics.
- Keep it read-only except for low-risk local settings.
- Guard access with an explicit local admin switch.

### Completion level

The project demonstrates the platform control plane expected from a platform-architecture case, without prematurely adding billing, distributed queues or microservices.

### Acceptance criteria

- Candidate navigation does not expose admin pages.
- Admin view is inaccessible unless the admin switch is enabled.
- Admin shows scenario, model, tool, quota, trace and evaluation summaries from real project data.
- Admin pages do not mutate production-like data except documented local settings.
- Tests cover access control and key summaries.
- All prior acceptance tests remain green.

## Change control

- Do not start the next step until the current step passes all gates.
- Do not add distributed infrastructure unless a measured blocker requires it.
- Any scope deviation must be documented with the reason and its impact on acceptance.
- Keep existing tests green; add tests for every new product capability.
