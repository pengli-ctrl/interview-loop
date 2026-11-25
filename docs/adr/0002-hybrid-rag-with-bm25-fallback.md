# ADR-002: Hybrid RAG with BM25 Fallback

## Status

Accepted

## Context

The application uses resumes as per-interview context. Local embedding models improve semantic retrieval but may be unavailable, expensive to download, or blocked by network restrictions.

## Decision

Use:

1. BM25 keyword retrieval as the always-available baseline.
2. FAISS plus a local embedding model when a model is already cached.
3. Automatic fallback to BM25 when vector loading fails.

## Consequences

Positive:

- upload remains usable offline;
- no mandatory model download;
- predictable first-use behavior;
- retrieval path can be tested independently.

Negative:

- BM25 has weaker semantic recall;
- retrieval quality can differ between environments.

## Follow-up

Add retrieval evaluation metrics such as Recall@K, MRR, and NDCG over a golden resume/question dataset.
