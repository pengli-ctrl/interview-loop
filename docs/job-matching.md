# Job Description and Resume Matching

The matcher lives in `interview_loop/core/job_match.py`.

## Pipeline

1. Normalize JD and resume text.
2. Extract canonical skills using the technical skill catalog.
3. Compare JD skills with resume evidence.
4. Produce matched, missing and bonus skills.
5. Generate risk areas and suggested interview focus.
6. Pass the job context into stage-aware question prompts.

## Score

`match_score = matched JD skills / total JD skills * 100`.

Levels:

- good: 70 and above;
- partial: 40-69;
- poor: below 40.

## Validation

A JD is rejected when it is too short or contains no supported skill keywords. Resume absence does not block the interview, but produces a risk and a zero match score.

## API

`POST /v1/job-match` accepts `job_description` and `resume_text` and returns the complete match report.
