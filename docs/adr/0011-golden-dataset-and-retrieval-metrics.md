# ADR-011: Golden Dataset and Retrieval Metrics

## Status

Accepted

## Context

Prompt changes, chunking changes, embedding changes, and fallback behavior can improve one case while regressing another. Without a golden dataset, RAG quality is judged by anecdotal screenshots.

## Decision

Maintain a versioned retrieval golden dataset and measure:

- Precision@K
- Recall@K
- MRR
- Hit Rate

The evaluation layer is pure and provider-independent. The sample CLI uses BM25 to demonstrate the workflow.

## Consequences

Positive:

- retrieval changes become comparable;
- PRs can include metric deltas;
- future embedding and reranker changes can be evaluated against the same cases;
- human-reviewed score calibration has a data foundation.

Negative:

- the current dataset is small and synthetic;
- metrics only cover retrieval, not final answer quality;
- production requires larger reviewed datasets.

## Follow-up

Expand the dataset with synthetic resumes, real interviewer-reviewed cases, and LLM rubric calibration.
