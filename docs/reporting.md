# Structured Reporting and Growth

## Report pipeline

`interview_loop/evaluation/interview_report.py` builds a deterministic report from:

- interviewer/candidate turns;
- scenario Rubric dimensions and weights;
- weak tags;
- JD match gaps.

## Output

- overall score;
- dimension scores and weights;
- evidence excerpts;
- strengths;
- risks;
- prioritized action plan;
- summary.

## Growth

Session records with `structured_report.overall_score` feed the growth chart. Consecutive sessions compare weak tags into new, resolved and persistent areas.

Old records without `structured_report` are skipped from trends but remain readable.
