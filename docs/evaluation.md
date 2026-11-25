# Evaluation

## Retrieval Metrics

The project exposes pure evaluation utilities for:

- Precision@K
- Recall@K
- MRR
- Hit Rate

Golden dataset:

`datasets/rag_golden.json`

Run the retrieval evaluation:

```bash
python scripts/evaluate_rag.py
```

## Rubric Weighted Score

`interview_loop/evaluation/rubric.py` supports weighted dimensions, such as:

- architecture depth: 30%;
- implementation detail: 25%;
- trade-off reasoning: 25%;
- communication: 20%.

This creates a path for calibrating LLM scores against human-reviewed examples.
