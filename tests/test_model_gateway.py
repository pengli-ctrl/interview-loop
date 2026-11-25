"""测试模块，覆盖模型网关相关行为和回归场景。"""
import pytest

from interview_loop.platform.model_gateway import (
    BudgetExceededError,
    CircuitBreakerPolicy,
    ModelGateway,
    ModelProfile,
    ModelUnavailableError,
    TenantQuota,
    TenantQuotaExceededError,
    TenantQuotaStore,
    UsageBudget,
    estimate_tokens,
)


def test_model_gateway_routes_tasks():
    """验证模型网关路由任务。"""
    gateway = ModelGateway(completer=lambda system_prompt, user_msg: f"{system_prompt}|{user_msg}")
    result = gateway.complete("review", "system", "user")
    assert result.content == "system|user"
    assert result.task == "review"
    assert result.provider == "default"
    assert result.model
    assert result.estimated_input_tokens > 0
    assert result.tenant_id == "local"


def test_unknown_task_uses_default_profile():
    """验证未知任务使用默认模型配置。"""
    gateway = ModelGateway(completer=lambda system_prompt, user_msg: "ok")
    result = gateway.complete("custom", "system", "user")
    assert result.prompt_version == "custom-v1"


def test_retry_recovers_from_transient_provider_error():
    """验证重试恢复从瞬时Provider错误。

    Raises:
        RuntimeError: 当输入、状态或外部依赖不满足要求时抛出 RuntimeError。

    """
    calls = []

    def flaky(system_prompt, user_msg):
        """构造按次数失败的模型调用替身。

        Args:
            system_prompt: `system_prompt` 输入参数，类型为 未标注。
            user_msg: `user_msg` 输入参数，类型为 未标注。

        Returns:
            函数处理结果，类型为 未标注。

        Raises:
            RuntimeError: 当输入、状态或外部依赖不满足要求时抛出 RuntimeError。

        """
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
    """验证失败后回退到下一个 Provider。

    Raises:
        RuntimeError: 当输入、状态或外部依赖不满足要求时抛出 RuntimeError。

    """
    def unavailable(system_prompt, user_msg):
        """构造始终不可用的模型调用替身。

        Args:
            system_prompt: `system_prompt` 输入参数，类型为 未标注。
            user_msg: `user_msg` 输入参数，类型为 未标注。

        Raises:
            RuntimeError: 当输入、状态或外部依赖不满足要求时抛出 RuntimeError。

        """
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
    """验证所有 Provider 失败时抛出带尝试详情的异常。"""
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


def test_circuit_opens_after_threshold_and_skips_provider():
    """验证熔断打开之后阈值和跳过Provider。

    Raises:
        RuntimeError: 当输入、状态或外部依赖不满足要求时抛出 RuntimeError。

    """
    clock = [0.0]
    calls = []

    def failing(system_prompt, user_msg):
        """构造始终失败的模型调用替身。

        Args:
            system_prompt: `system_prompt` 输入参数，类型为 未标注。
            user_msg: `user_msg` 输入参数，类型为 未标注。

        Raises:
            RuntimeError: 当输入、状态或外部依赖不满足要求时抛出 RuntimeError。

        """
        calls.append(1)
        raise RuntimeError("down")

    gateway = ModelGateway(
        providers={"primary": failing},
        profiles={
            "review": [
                ModelProfile("primary", "model-a", "review-v1", max_retries=0)
            ]
        },
        circuit_breaker_policy=CircuitBreakerPolicy(
            failure_threshold=2,
            cooldown_seconds=10,
        ),
        clock=lambda: clock[0],
    )

    for _ in range(2):
        with pytest.raises(ModelUnavailableError):
            gateway.complete("review", "system", "user")
    with pytest.raises(ModelUnavailableError, match="circuit open"):
        gateway.complete("review", "system", "user")
    assert len(calls) == 2


def test_circuit_half_open_recovers_after_cooldown():
    """验证熔断半打开恢复之后冷却。

    Raises:
        RuntimeError: 当输入、状态或外部依赖不满足要求时抛出 RuntimeError。

    """
    clock = [0.0]
    calls = []

    def flaky(system_prompt, user_msg):
        """构造按次数失败的模型调用替身。

        Args:
            system_prompt: `system_prompt` 输入参数，类型为 未标注。
            user_msg: `user_msg` 输入参数，类型为 未标注。

        Returns:
            函数处理结果，类型为 未标注。

        Raises:
            RuntimeError: 当输入、状态或外部依赖不满足要求时抛出 RuntimeError。

        """
        calls.append(1)
        if len(calls) <= 2:
            raise RuntimeError("down")
        return "recovered"

    gateway = ModelGateway(
        providers={"primary": flaky},
        profiles={
            "review": [
                ModelProfile("primary", "model-a", "review-v1", max_retries=0)
            ]
        },
        circuit_breaker_policy=CircuitBreakerPolicy(
            failure_threshold=2,
            cooldown_seconds=10,
        ),
        clock=lambda: clock[0],
    )

    for _ in range(2):
        with pytest.raises(ModelUnavailableError):
            gateway.complete("review", "system", "user")
    clock[0] = 11
    result = gateway.complete("review", "system", "user")
    assert result.content == "recovered"
    assert len(calls) == 3


def test_tenant_quota_is_isolated_between_tenants():
    """验证租户配额判断隔离之间租户。"""
    clock = [0.0]
    store = TenantQuotaStore(
        TenantQuota(max_tokens=5, max_cost=100.0),
        clock=lambda: clock[0],
    )
    store.add("tenant-a", 4, 0)
    gateway = ModelGateway(
        completer=lambda system_prompt, user_msg: "ok",
        tenant_quota_store=store,
    )

    with pytest.raises(TenantQuotaExceededError):
        gateway.complete("review", "system", "user", tenant_id="tenant-a")

    result = gateway.complete("review", "system", "user", tenant_id="tenant-b")
    assert result.content == "ok"
    assert result.tenant_id == "tenant-b"


def test_tenant_quota_window_resets_usage():
    """验证租户配额窗口重置用量。"""
    clock = [0.0]
    store = TenantQuotaStore(
        TenantQuota(max_tokens=5, max_cost=100.0, window_seconds=10),
        clock=lambda: clock[0],
    )
    store.add("tenant-a", 5, 0)
    with pytest.raises(TenantQuotaExceededError):
        store.check("tenant-a", 1, 0)
    clock[0] = 11
    store.check("tenant-a", 1, 0)
    assert store.snapshot("tenant-a")["used_tokens"] == 0


def test_budget_accumulates_usage():
    """验证预算累加用量。"""
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
    """验证预算拒绝之后调用超限和记录实际用量。"""
    budget = UsageBudget(max_tokens=2, max_cost=100.0)
    gateway = ModelGateway(completer=lambda system_prompt, user_msg: "ok")
    with pytest.raises(BudgetExceededError):
        gateway.complete("review", "system", "user", budget=budget)
    assert budget.used_tokens == 3


def test_estimate_tokens():
    """验证估算Token。"""
    assert estimate_tokens("12345678") == 2
    assert estimate_tokens("") == 1
