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


## Quality Calibration

`datasets/quality_golden.json` stores human-reviewed dimension scores and model scores. Run:

```bash
python scripts/evaluate_quality.py
```

The gate fails when weighted MAE or per-case error exceeds configured thresholds.

## Agent Metrics

`interview_loop/evaluation/agent_metrics.py` summarizes:

- latency P50/P95;
- token and estimated cost;
- failure and retry rate;
- duplicate question rate;
- stage adherence.

The authenticated endpoint `GET /v1/metrics` returns the summary for the current tenant.

## Trace Replay

`interview_loop/evaluation/replay.py` reconstructs stage order and completion events from an AgentRun JSON export without calling a model or tool provider.
