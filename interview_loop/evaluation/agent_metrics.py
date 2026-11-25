import math

from interview_loop.core.question_engine import questions_too_similar


def percentile(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    position = (len(ordered) - 1) * max(0.0, min(1.0, quantile))
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return float(ordered[lower])
    weight = position - lower
    return float(ordered[lower] * (1 - weight) + ordered[upper] * weight)


def summarize_agent_runs(runs: list[dict]) -> dict:
    events = [
        event
        for run in runs
        for event in run.get("events", [])
        if isinstance(event, dict)
    ]
    model_calls = [event for event in events if event.get("event_type") == "model.call"]
    tool_calls = [
        event
        for event in events
        if event.get("event_type")
        in {"tool.completed", "tool.failed", "tool.cache_hit"}
    ]
    tool_retries = [
        event for event in events if event.get("event_type") == "tool.retry"
    ]
    questions = [
        str(event.get("payload", {}).get("question", "")).strip()
        for event in events
        if event.get("event_type") == "question.generated"
    ]
    questions = [question for question in questions if question]
    duplicate_pairs = 0
    duplicate_questions = 0
    for index, question in enumerate(questions):
        is_duplicate = any(
            questions_too_similar(question, previous)
            for previous in questions[:index]
        )
        if is_duplicate:
            duplicate_questions += 1
        duplicate_pairs += index
    latencies = [
        float(event.get("payload", {}).get("latency_ms", 0))
        for event in model_calls
    ]
    input_tokens = sum(
        int(event.get("payload", {}).get("estimated_input_tokens", 0))
        for event in model_calls
    )
    output_tokens = sum(
        int(event.get("payload", {}).get("estimated_output_tokens", 0))
        for event in model_calls
    )
    estimated_cost = sum(
        float(event.get("payload", {}).get("estimated_cost", 0))
        for event in model_calls
    )
    total_runs = len(runs)
    failed_runs = sum(run.get("status") == "failed" for run in runs)
    completed_runs = sum(run.get("status") == "completed" for run in runs)
    model_retries = sum(
        int(event.get("payload", {}).get("attempts", 1)) > 1
        for event in model_calls
    )
    stage_aware_questions = sum(
        "stage_index" in event.get("payload", {})
        and "stage_name" in event.get("payload", {})
        for event in events
        if event.get("event_type") == "question.generated"
    )
    denominator = max(1, len(model_calls) + len(tool_calls))
    return {
        "run_count": total_runs,
        "completed_runs": completed_runs,
        "failed_runs": failed_runs,
        "failure_rate": failed_runs / total_runs if total_runs else 0.0,
        "model_call_count": len(model_calls),
        "tool_call_count": len(tool_calls),
        "latency_p50_ms": percentile(latencies, 0.50),
        "latency_p95_ms": percentile(latencies, 0.95),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "estimated_cost": estimated_cost,
        "retry_rate": (model_retries + len(tool_retries)) / denominator,
        "question_count": len(questions),
        "duplicate_question_rate": (
            duplicate_questions / len(questions) if questions else 0.0
        ),
        "stage_adherence": (
            stage_aware_questions / len(questions) if questions else 0.0
        ),
        "question_pair_count": duplicate_pairs,
    }
