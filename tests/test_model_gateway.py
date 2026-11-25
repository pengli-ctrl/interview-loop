import pytest

from interview_loop.platform.model_gateway import (
    BudgetExceededError,
    ModelGateway,
    ModelProfile,
    ModelUnavailableError,
    UsageBudget,
    estimate_tokens,
)


def test_model_gateway_routes_tasks():
    gateway = ModelGateway(completer=lambda system_prompt, user_msg: f"{system_prompt}|{user_msg}")
    result = gateway.complete("review", "system", "user")
    assert result.content == "system|user"
    assert result.task == "review"
    assert result.provider == "default"
    assert result.model
    assert result.estimated_input_tokens > 0


def test_unknown_task_uses_default_profile():
    gateway = ModelGateway(completer=lambda system_prompt, user_msg: "ok")
    result = gateway.complete("custom", "system", "user")
    assert result.prompt_version == "custom-v1"


def test_retry_recovers_from_transient_provider_error():
    calls = []

    def flaky(system_prompt, user_msg):
        calls.append((system_prompt, user_msg))
        if len(calls) == 1:
            raise RuntimeError("temporary failure")
        return "recovered"

    gateway = ModelGateway(
        providers={"primary": flaky},
        profiles={
            "review": [
                ModelProfile("primary", "model-a", "review-v2", max_retries=1)
            ]
        },
    )
    result = gateway.complete("review", "system", "user")
    assert result.content == "recovered"
    assert result.attempts == 2
    assert result.provider == "primary"


def test_fallback_moves_to_next_provider():
    def unavailable(system_prompt, user_msg):
        raise RuntimeError("provider down")

    gateway = ModelGateway(
        providers={
            "primary": unavailable,
            "backup": lambda system_prompt, user_msg: "fallback result",
        },
        profiles={
            "question": [
                ModelProfile("primary", "model-a", "question-v1", max_retries=0),
                ModelProfile("backup", "model-b", "question-v2", max_retries=0),
            ]
        },
    )
    result = gateway.complete("question", "system", "user")
    assert result.content == "fallback result"
    assert result.provider == "backup"
    assert result.model == "model-b"
    assert result.attempts == 2


def test_all_providers_failed_raises_with_attempt_details():
    gateway = ModelGateway(
        providers={"primary": lambda system_prompt, user_msg: (_ for _ in ()).throw(RuntimeError("down"))},
        profiles={
            "review": [
                ModelProfile("primary", "model-a", "review-v1", max_retries=0)
            ]
        },
    )
    with pytest.raises(ModelUnavailableError, match="primary attempt 1: down"):
        gateway.complete("review", "system", "user")


def test_budget_accumulates_usage():
    budget = UsageBudget(max_tokens=10000, max_cost=1.0)
    gateway = ModelGateway(completer=lambda system_prompt, user_msg: "answer")
    first = gateway.complete("review", "system", "user", budget=budget)
    second = gateway.complete("review", "system", "user", budget=budget)
    assert budget.used_tokens == (
        first.estimated_input_tokens
        + first.estimated_output_tokens
        + second.estimated_input_tokens
        + second.estimated_output_tokens
    )
    assert budget.used_cost == pytest.approx(first.estimated_cost + second.estimated_cost)
    assert budget.to_dict()["remaining_tokens"] == 10000 - budget.used_tokens


def test_budget_rejects_post_call_overrun_and_records_actual_usage():
    budget = UsageBudget(max_tokens=2, max_cost=100.0)
    gateway = ModelGateway(completer=lambda system_prompt, user_msg: "ok")
    with pytest.raises(BudgetExceededError):
        gateway.complete("review", "system", "user", budget=budget)
    assert budget.used_tokens == 3


def test_estimate_tokens():
    assert estimate_tokens("12345678") == 2
    assert estimate_tokens("") == 1
