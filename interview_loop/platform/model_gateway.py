import os
from dataclasses import dataclass
from time import perf_counter
from typing import Callable

DEFAULT_MODEL = os.getenv("deepseek_model", "deepseek-chat")


@dataclass(frozen=True)
class ModelProfile:
    task: str
    model: str
    prompt_version: str
    temperature: float = 0.3


@dataclass(frozen=True)
class ModelResult:
    content: str
    task: str
    model: str
    prompt_version: str
    latency_ms: int
    estimated_input_tokens: int
    estimated_output_tokens: int


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


class ModelGateway:
    def __init__(self, completer: Callable[..., str] | None = None) -> None:
        if completer is None:
            from interview_loop.services.llm import llm_call

            completer = llm_call
        self._completer = completer
        self._profiles = {
            "question": ModelProfile("question", DEFAULT_MODEL, "question-v1"),
            "tagging": ModelProfile("tagging", DEFAULT_MODEL, "tagging-v1"),
            "review": ModelProfile("review", DEFAULT_MODEL, "review-v1"),
        }

    def complete(self, task: str, system_prompt: str, user_msg: str) -> ModelResult:
        profile = self._profiles.get(task, ModelProfile(task, DEFAULT_MODEL, f"{task}-v1"))
        started = perf_counter()
        content = self._completer(system_prompt, user_msg)
        latency_ms = int((perf_counter() - started) * 1000)
        return ModelResult(
            content=content,
            task=task,
            model=profile.model,
            prompt_version=profile.prompt_version,
            latency_ms=latency_ms,
            estimated_input_tokens=estimate_tokens(system_prompt + user_msg),
            estimated_output_tokens=estimate_tokens(content),
        )
