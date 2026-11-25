import json
from pathlib import Path

import pytest

from interview_loop.evaluation.agent_metrics import (
    percentile,
    summarize_agent_runs,
)
from interview_loop.evaluation.quality import evaluate_quality
from interview_loop.evaluation.replay import ReplayError, replay_agent_run


def test_quality_golden_dataset_passes_thresholds():
    root = Path(__file__).resolve().parents[1]
    dataset = json.loads(
        (root / "datasets" / "quality_golden.json").read_text(encoding="utf-8")
    )
    report = evaluate_quality(dataset)
    assert report.case_count >= 3
    assert report.human_review_passed
    assert report.passed


def test_percentile_interpolates_values():
    assert percentile([100, 300], 0.5) == 200
    assert percentile([100, 300], 0.95) == 290


def test_summarize_agent_runs_reports_latency_quality_and_failures():
    runs = [
        {
            "status": "completed",
            "events": [
                {
                    "event_type": "model.call",
                    "payload": {
                        "latency_ms": 100,
                        "estimated_input_tokens": 10,
                        "estimated_output_tokens": 5,
                        "estimated_cost": 0.1,
                        "attempts": 1,
                    },
                },
                {
                    "event_type": "question.generated",
                    "payload": {
                        "question": "Explain RAG.",
                        "stage_index": 0,
                        "stage_name": "self_intro",
                    },
                },
                {
                    "event_type": "question.generated",
                    "payload": {
                        "question": "Explain RAG.",
                        "stage_index": 1,
                        "stage_name": "project",
                    },
                },
            ],
        },
        {
            "status": "failed",
            "events": [
                {
                    "event_type": "model.call",
                    "payload": {
                        "latency_ms": 300,
                        "attempts": 2,
                    },
                },
                {"event_type": "tool.retry", "payload": {}},
            ],
        },
    ]
    report = summarize_agent_runs(runs)
    assert report["run_count"] == 2
    assert report["failure_rate"] == 0.5
    assert report["latency_p50_ms"] == 200
    assert report["latency_p95_ms"] == 290
    assert report["duplicate_question_rate"] == 0.5
    assert report["stage_adherence"] == 1.0
    assert report["retry_rate"] > 0


def test_trace_replay_reconstructs_completed_stage_sequence():
    run = {
        "run_id": "run-1",
        "trace_id": "trace-1",
        "status": "completed",
        "events": [
            {
                "event_type": "stage.transition",
                "payload": {"from_index": 0, "to_index": 1},
            },
            {
                "event_type": "question.generated",
                "payload": {"stage_index": 1, "stage_name": "project"},
            },
            {"event_type": "evaluation.completed", "payload": {}},
            {"event_type": "record.exported", "payload": {}},
            {"event_type": "run.completed", "payload": {}},
        ],
    }
    report = replay_agent_run(run)
    assert report.stage_sequence == [0, 1]
    assert report.question_count == 1
    assert report.evaluation_completed
    assert report.record_exported
    assert report.completed


def test_trace_replay_rejects_invalid_transition():
    run = {
        "run_id": "run-1",
        "trace_id": "trace-1",
        "status": "running",
        "events": [
            {
                "event_type": "stage.transition",
                "payload": {"from_index": 2, "to_index": 3},
            }
        ],
    }
    with pytest.raises(ReplayError):
        replay_agent_run(run)
