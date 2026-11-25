import os
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


def default_usage_budget() -> UsageBudget:
    return UsageBudget(
        max_tokens=int(os.getenv("llm_max_tokens_per_run", "200000")),
        max_cost=float(os.getenv("llm_max_cost_per_run", "5.0")),
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

            retries = max(0, int(profile.max_retries))
            for attempt in range(1, retries + 2):
                total_attempts += 1
                started = perf_counter()
                try:
                    content = provider(system_prompt, user_msg)
                except Exception as exc:
                    errors.append(f"{profile.provider} attempt {attempt}: {exc}")
                    continue

                latency_ms = int((perf_counter() - started) * 1000)
                if not isinstance(content, str) or not content.strip():
                    errors.append(
                        f"{profile.provider} attempt {attempt}: empty model response"
                    )
                    continue

                output_tokens = estimate_tokens(content)
                cost = (
                    input_tokens * profile.input_cost_per_million
                    + output_tokens * profile.output_cost_per_million
                ) / 1_000_000
                if budget is not None:
                    budget.add(input_tokens + output_tokens, cost)
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
                )

        detail = "; ".join(errors) or "no model profiles configured"
        raise ModelUnavailableError(
            f"All model providers failed for task={task}: {detail}"
        )
