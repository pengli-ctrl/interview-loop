"""模型网关模块，负责路由、重试、熔断、预算、租户额度、成本和调用遥测。"""
import os
import threading
from dataclasses import dataclass
from time import perf_counter
from typing import Callable

DEFAULT_MODEL = os.getenv("deepseek_model", "deepseek-chat")
DEFAULT_INPUT_COST = float(os.getenv("llm_input_cost_per_million", "3.0"))
DEFAULT_OUTPUT_COST = float(os.getenv("llm_output_cost_per_million", "6.0"))


class ModelUnavailableError(RuntimeError):
    """表示模型不可用的异常。"""
    pass


class BudgetExceededError(RuntimeError):
    """表示预算超限的异常。"""
    pass


class TenantQuotaExceededError(BudgetExceededError):
    """表示租户配额超限的异常。"""
    pass


@dataclass(frozen=True)
class ModelProfile:
    """模型调用配置。"""
    provider: str
    model: str
    prompt_version: str
    temperature: float = 0.3
    input_cost_per_million: float = DEFAULT_INPUT_COST
    output_cost_per_million: float = DEFAULT_OUTPUT_COST
    max_retries: int = 1


@dataclass(frozen=True)
class ModelResult:
    """模型调用结果。"""
    content: str
    task: str
    provider: str
    model: str
    prompt_version: str
    latency_ms: int
    estimated_input_tokens: int
    estimated_output_tokens: int
    estimated_cost: float
    attempts: int
    tenant_id: str = "local"


@dataclass
class UsageBudget:
    """单次运行用量预算。"""
    max_tokens: int
    max_cost: float
    used_tokens: int = 0
    used_cost: float = 0.0

    @property
    def remaining_tokens(self) -> int:
        """剩余 Token 数。

        Returns:
            函数处理结果，类型为 int。

        """
        return max(0, self.max_tokens - self.used_tokens)

    @property
    def remaining_cost(self) -> float:
        """剩余成本。

        Returns:
            函数处理结果，类型为 float。

        """
        return max(0.0, self.max_cost - self.used_cost)

    def check(self, tokens: int, cost: float) -> None:
        """检查预算是否足够。

        Args:
            tokens: `tokens` 输入参数，类型为 int。
            cost: `cost` 输入参数，类型为 float。

        Raises:
            BudgetExceededError: 当输入、状态或外部依赖不满足要求时抛出 BudgetExceededError。

        """
        next_tokens = self.used_tokens + max(0, int(tokens))
        next_cost = self.used_cost + max(0.0, float(cost))
        if next_tokens > self.max_tokens or next_cost > self.max_cost:
            raise BudgetExceededError(
                f"Model budget exceeded: tokens={next_tokens}/{self.max_tokens}, "
                f"cost={next_cost:.4f}/{self.max_cost:.4f}"
            )

    def add(self, tokens: int, cost: float) -> None:
        """累加用量并在超限时抛出异常。

        Args:
            tokens: `tokens` 输入参数，类型为 int。
            cost: `cost` 输入参数，类型为 float。

        Raises:
            BudgetExceededError: 当输入、状态或外部依赖不满足要求时抛出 BudgetExceededError。

        """
        self.used_tokens += max(0, int(tokens))
        self.used_cost += max(0.0, float(cost))
        if self.used_tokens > self.max_tokens or self.used_cost > self.max_cost:
            raise BudgetExceededError(
                f"Model budget exceeded: tokens={self.used_tokens}/{self.max_tokens}, "
                f"cost={self.used_cost:.4f}/{self.max_cost:.4f}"
            )

    def to_dict(self) -> dict:
        """转换为字典。

        Returns:
            函数处理结果，类型为 dict。

        """
        return {
            "max_tokens": self.max_tokens,
            "used_tokens": self.used_tokens,
            "remaining_tokens": self.remaining_tokens,
            "max_cost": self.max_cost,
            "used_cost": round(self.used_cost, 6),
            "remaining_cost": round(self.remaining_cost, 6),
        }


@dataclass(frozen=True)
class TenantQuota:
    """租户滚动配额。"""
    max_tokens: int
    max_cost: float
    window_seconds: float = 86400


@dataclass
class TenantUsage:
    """租户滚动用量。"""
    window_started: float
    used_tokens: int = 0
    used_cost: float = 0.0


class TenantQuotaStore:
    """进程内租户配额存储。"""

    def __init__(
        self,
        quota: TenantQuota,
        *,
        clock: Callable[[], float] = perf_counter,
    ) -> None:
        """初始化租户配额存储。

        Args:
            quota: `quota` 输入参数，类型为 TenantQuota。
            clock: `clock` 关键字参数，类型为 Callable[[], float]。

        """
        self.quota = quota
        self._clock = clock
        self._lock = threading.Lock()
        self._usage: dict[str, TenantUsage] = {}

    def _current_usage(self, tenant_id: str) -> TenantUsage:
        """内部辅助：读取当前窗口用量。

        Args:
            tenant_id: `tenant_id` 输入参数，类型为 str。

        Returns:
            函数处理结果，类型为 TenantUsage。

        """
        now = self._clock()
        usage = self._usage.get(tenant_id)
        if usage is None or now - usage.window_started >= self.quota.window_seconds:
            usage = TenantUsage(window_started=now)
            self._usage[tenant_id] = usage
        return usage

    def check(self, tenant_id: str, tokens: int, cost: float) -> None:
        """检查租户配额是否足够。

        Args:
            tenant_id: `tenant_id` 输入参数，类型为 str。
            tokens: `tokens` 输入参数，类型为 int。
            cost: `cost` 输入参数，类型为 float。

        Raises:
            TenantQuotaExceededError: 当输入、状态或外部依赖不满足要求时抛出 TenantQuotaExceededError。

        """
        with self._lock:
            usage = self._current_usage(tenant_id)
            next_tokens = usage.used_tokens + max(0, int(tokens))
            next_cost = usage.used_cost + max(0.0, float(cost))
            if (
                next_tokens > self.quota.max_tokens
                or next_cost > self.quota.max_cost
            ):
                raise TenantQuotaExceededError(
                    f"Tenant model quota exceeded for {tenant_id}: "
                    f"tokens={next_tokens}/{self.quota.max_tokens}, "
                    f"cost={next_cost:.4f}/{self.quota.max_cost:.4f}"
                )

    def add(self, tenant_id: str, tokens: int, cost: float) -> None:
        """累加租户用量并检查配额。

        Args:
            tenant_id: `tenant_id` 输入参数，类型为 str。
            tokens: `tokens` 输入参数，类型为 int。
            cost: `cost` 输入参数，类型为 float。

        """
        with self._lock:
            usage = self._current_usage(tenant_id)
            usage.used_tokens += max(0, int(tokens))
            usage.used_cost += max(0.0, float(cost))

    def snapshot(self, tenant_id: str) -> dict:
        """返回当前租户用量快照。

        Args:
            tenant_id: `tenant_id` 输入参数，类型为 str。

        Returns:
            函数处理结果，类型为 dict。

        """
        with self._lock:
            usage = self._current_usage(tenant_id)
            return {
                "tenant_id": tenant_id,
                "window_seconds": self.quota.window_seconds,
                "max_tokens": self.quota.max_tokens,
                "used_tokens": usage.used_tokens,
                "max_cost": self.quota.max_cost,
                "used_cost": round(usage.used_cost, 6),
            }


@dataclass(frozen=True)
class CircuitBreakerPolicy:
    """熔断器策略。"""
    failure_threshold: int = 3
    cooldown_seconds: float = 30.0


@dataclass
class _ProviderCircuitState:
    """Provider 熔断状态。"""
    failures: int = 0
    opened_at: float | None = None


def default_usage_budget() -> UsageBudget:
    """创建默认单轮用量预算。

    Returns:
        函数处理结果，类型为 UsageBudget。

    """
    return UsageBudget(
        max_tokens=int(os.getenv("llm_max_tokens_per_run", "200000")),
        max_cost=float(os.getenv("llm_max_cost_per_run", "5.0")),
    )


def default_tenant_quota_store() -> TenantQuotaStore:
    """创建默认租户配额存储。

    Returns:
        函数处理结果，类型为 TenantQuotaStore。

    """
    return TenantQuotaStore(
        TenantQuota(
            max_tokens=int(os.getenv("llm_tenant_max_tokens", "1000000")),
            max_cost=float(os.getenv("llm_tenant_max_cost", "50.0")),
            window_seconds=float(os.getenv("llm_tenant_quota_window_seconds", "86400")),
        )
    )


def estimate_tokens(text: str) -> int:
    """粗略估算文本 Token 数。

    Args:
        text: `text` 输入参数，类型为 str。

    Returns:
        函数处理结果，类型为 int。

    """
    return max(1, len(text) // 4)


class ModelGateway:
    """模型网关。"""
    def __init__(
        self,
        completer: Callable[[str, str], str] | None = None,
        *,
        providers: dict[str, Callable[[str, str], str]] | None = None,
        profiles: dict[str, list[ModelProfile]] | None = None,
        circuit_breaker_policy: CircuitBreakerPolicy | None = None,
        tenant_quota_store: TenantQuotaStore | None = None,
        clock: Callable[[], float] = perf_counter,
    ) -> None:
        """初始化模型网关。

        Args:
            completer: `completer` 输入参数，类型为 Callable[[str, str], str] | None。
            providers: `providers` 关键字参数，类型为 dict[str, Callable[[str, str], str]] | None。
            profiles: `profiles` 关键字参数，类型为 dict[str, list[ModelProfile]] | None。
            circuit_breaker_policy: `circuit_breaker_policy` 关键字参数，类型为 CircuitBreakerPolicy | None。
            tenant_quota_store: `tenant_quota_store` 关键字参数，类型为 TenantQuotaStore | None。
            clock: `clock` 关键字参数，类型为 Callable[[], float]。

        """
        if providers is None:
            if completer is None:
                from interview_loop.services.llm import llm_call

                completer = llm_call
            providers = {"default": completer}
        self._providers = providers
        self._profiles = profiles or {
            task: [
                ModelProfile(
                    provider="default",
                    model=DEFAULT_MODEL,
                    prompt_version=f"{task}-v1",
                )
            ]
            for task in ("question", "tagging", "review")
        }
        self._breaker_policy = circuit_breaker_policy or CircuitBreakerPolicy(
            failure_threshold=max(
                1, int(os.getenv("llm_circuit_failure_threshold", "3"))
            ),
            cooldown_seconds=float(
                os.getenv("llm_circuit_cooldown_seconds", "30")
            ),
        )
        self._breaker_lock = threading.Lock()
        self._breaker_state: dict[str, _ProviderCircuitState] = {}
        self._tenant_quota_store = tenant_quota_store
        self._clock = clock

    def profiles_for(self, task: str) -> list[ModelProfile]:
        """返回指定任务的模型配置列表。

        Args:
            task: `task` 输入参数，类型为 str。

        Returns:
            函数处理结果，类型为 list[ModelProfile]。

        """
        return list(
            self._profiles.get(
                task,
                [ModelProfile("default", DEFAULT_MODEL, f"{task}-v1")],
            )
        )

    def complete(
        self,
        task: str,
        system_prompt: str,
        user_msg: str,
        *,
        budget: UsageBudget | None = None,
        tenant_id: str = "local",
    ) -> ModelResult:
        """按任务路由调用模型并返回结果。

        Args:
            task: `task` 输入参数，类型为 str。
            system_prompt: `system_prompt` 输入参数，类型为 str。
            user_msg: `user_msg` 输入参数，类型为 str。
            budget: `budget` 关键字参数，类型为 UsageBudget | None。
            tenant_id: `tenant_id` 关键字参数，类型为 str。

        Returns:
            函数处理结果，类型为 ModelResult。

        Raises:
            ModelUnavailableError: 当输入、状态或外部依赖不满足要求时抛出 ModelUnavailableError。

        """
        errors: list[str] = []
        total_attempts = 0
        input_tokens = estimate_tokens(system_prompt + user_msg)

        for profile in self.profiles_for(task):
            provider = self._providers.get(profile.provider)
            if provider is None:
                errors.append(f"provider {profile.provider} is not configured")
                continue

            input_cost = input_tokens * profile.input_cost_per_million / 1_000_000
            if budget is not None:
                budget.check(input_tokens, input_cost)
            if self._tenant_quota_store is not None:
                self._tenant_quota_store.check(tenant_id, input_tokens, input_cost)

            retries = max(0, int(profile.max_retries))
            for attempt in range(1, retries + 2):
                if not self._circuit_available(profile.provider):
                    errors.append(f"provider {profile.provider} circuit open")
                    break
                total_attempts += 1
                started = perf_counter()
                try:
                    content = provider(system_prompt, user_msg)
                except Exception as exc:
                    self._record_provider_failure(profile.provider)
                    errors.append(f"{profile.provider} attempt {attempt}: {exc}")
                    continue

                latency_ms = int((perf_counter() - started) * 1000)
                if not isinstance(content, str) or not content.strip():
                    self._record_provider_failure(profile.provider)
                    errors.append(
                        f"{profile.provider} attempt {attempt}: empty model response"
                    )
                    continue

                self._record_provider_success(profile.provider)
                output_tokens = estimate_tokens(content)
                cost = (
                    input_tokens * profile.input_cost_per_million
                    + output_tokens * profile.output_cost_per_million
                ) / 1_000_000
                if budget is not None:
                    budget.add(input_tokens + output_tokens, cost)
                if self._tenant_quota_store is not None:
                    self._tenant_quota_store.add(
                        tenant_id,
                        input_tokens + output_tokens,
                        cost,
                    )
                return ModelResult(
                    content=content,
                    task=task,
                    provider=profile.provider,
                    model=profile.model,
                    prompt_version=profile.prompt_version,
                    latency_ms=latency_ms,
                    estimated_input_tokens=input_tokens,
                    estimated_output_tokens=output_tokens,
                    estimated_cost=cost,
                    attempts=total_attempts,
                    tenant_id=tenant_id,
                )

        detail = "; ".join(errors) or "no model profiles configured"
        raise ModelUnavailableError(
            f"All model providers failed for task={task}: {detail}"
        )

    def _circuit_available(self, provider_name: str) -> bool:
        """内部辅助：判断 Provider 是否允许调用。

        Args:
            provider_name: `provider_name` 输入参数，类型为 str。

        Returns:
            函数处理结果，类型为 bool。

        """
        if self._breaker_policy.failure_threshold <= 0:
            return True
        with self._breaker_lock:
            state = self._breaker_state.setdefault(
                provider_name,
                _ProviderCircuitState(),
            )
            if state.opened_at is None:
                return True
            elapsed = self._clock() - state.opened_at
            if elapsed < self._breaker_policy.cooldown_seconds:
                return False
            state.opened_at = None
            state.failures = max(0, self._breaker_policy.failure_threshold - 1)
            return True

    def _record_provider_failure(self, provider_name: str) -> None:
        """记录 Provider 失败并更新熔断状态。

        Args:
            provider_name: `provider_name` 输入参数，类型为 str。

        """
        if self._breaker_policy.failure_threshold <= 0:
            return
        with self._breaker_lock:
            state = self._breaker_state.setdefault(
                provider_name,
                _ProviderCircuitState(),
            )
            state.failures += 1
            if state.failures >= self._breaker_policy.failure_threshold:
                state.opened_at = self._clock()

    def _record_provider_success(self, provider_name: str) -> None:
        """记录 Provider 成功并重置熔断状态。

        Args:
            provider_name: `provider_name` 输入参数，类型为 str。

        """
        with self._breaker_lock:
            self._breaker_state[provider_name] = _ProviderCircuitState()
