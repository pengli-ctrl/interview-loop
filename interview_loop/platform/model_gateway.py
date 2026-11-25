import os
import threading
from dataclasses import dataclass
from time import perf_counter
from typing import Callable

DEFAULT_MODEL = os.getenv("deepseek_model", "deepseek-chat")
DEFAULT_INPUT_COST = float(os.getenv("llm_input_cost_per_million", "3.0"))
DEFAULT_OUTPUT_COST = float(os.getenv("llm_output_cost_per_million", "6.0"))


class ModelUnavailableError(RuntimeError):
    pass


class BudgetExceededError(RuntimeError):
    pass


class TenantQuotaExceededError(BudgetExceededError):
    pass


@dataclass(frozen=True)
class ModelProfile:
    provider: str
    model: str
    prompt_version: str
    temperature: float = 0.3
    input_cost_per_million: float = DEFAULT_INPUT_COST
    output_cost_per_million: float = DEFAULT_OUTPUT_COST
    max_retries: int = 1


@dataclass(frozen=True)
class ModelResult:
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
    max_tokens: int
    max_cost: float
    used_tokens: int = 0
    used_cost: float = 0.0

    @property
    def remaining_tokens(self) -> int:
        return max(0, self.max_tokens - self.used_tokens)

    @property
    def remaining_cost(self) -> float:
        return max(0.0, self.max_cost - self.used_cost)

    def check(self, tokens: int, cost: float) -> None:
        next_tokens = self.used_tokens + max(0, int(tokens))
        next_cost = self.used_cost + max(0.0, float(cost))
        if next_tokens > self.max_tokens or next_cost > self.max_cost:
            raise BudgetExceededError(
                f"Model budget exceeded: tokens={next_tokens}/{self.max_tokens}, "
                f"cost={next_cost:.4f}/{self.max_cost:.4f}"
            )

    def add(self, tokens: int, cost: float) -> None:
        """Charge actual usage, then reject subsequent work if the limit was crossed."""
        self.used_tokens += max(0, int(tokens))
        self.used_cost += max(0.0, float(cost))
        if self.used_tokens > self.max_tokens or self.used_cost > self.max_cost:
            raise BudgetExceededError(
                f"Model budget exceeded: tokens={self.used_tokens}/{self.max_tokens}, "
                f"cost={self.used_cost:.4f}/{self.max_cost:.4f}"
            )

    def to_dict(self) -> dict:
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
    max_tokens: int
    max_cost: float
    window_seconds: float = 86400


@dataclass
class TenantUsage:
    window_started: float
    used_tokens: int = 0
    used_cost: float = 0.0


class TenantQuotaStore:
    """Process-local rolling tenant quota used by the current single-process slice."""

    def __init__(
        self,
        quota: TenantQuota,
        *,
        clock: Callable[[], float] = perf_counter,
    ) -> None:
        self.quota = quota
        self._clock = clock
        self._lock = threading.Lock()
        self._usage: dict[str, TenantUsage] = {}

    def _current_usage(self, tenant_id: str) -> TenantUsage:
        now = self._clock()
        usage = self._usage.get(tenant_id)
        if usage is None or now - usage.window_started >= self.quota.window_seconds:
            usage = TenantUsage(window_started=now)
            self._usage[tenant_id] = usage
        return usage

    def check(self, tenant_id: str, tokens: int, cost: float) -> None:
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
        with self._lock:
            usage = self._current_usage(tenant_id)
            usage.used_tokens += max(0, int(tokens))
            usage.used_cost += max(0.0, float(cost))

    def snapshot(self, tenant_id: str) -> dict:
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
    failure_threshold: int = 3
    cooldown_seconds: float = 30.0


@dataclass
class _ProviderCircuitState:
    failures: int = 0
    opened_at: float | None = None


def default_usage_budget() -> UsageBudget:
    return UsageBudget(
        max_tokens=int(os.getenv("llm_max_tokens_per_run", "200000")),
        max_cost=float(os.getenv("llm_max_cost_per_run", "5.0")),
    )


def default_tenant_quota_store() -> TenantQuotaStore:
    return TenantQuotaStore(
        TenantQuota(
            max_tokens=int(os.getenv("llm_tenant_max_tokens", "1000000")),
            max_cost=float(os.getenv("llm_tenant_max_cost", "50.0")),
            window_seconds=float(os.getenv("llm_tenant_quota_window_seconds", "86400")),
        )
    )


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


class ModelGateway:
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
        with self._breaker_lock:
            self._breaker_state[provider_name] = _ProviderCircuitState()
