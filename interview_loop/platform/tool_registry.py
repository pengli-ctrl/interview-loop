from dataclasses import dataclass
from time import perf_counter
from typing import Any, Callable


class ToolNotFoundError(LookupError):
    pass


class ToolExecutionError(RuntimeError):
    pass


class ToolPermissionError(PermissionError):
    pass


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    handler: Callable[..., Any]
    version: str = "v1"
    timeout_seconds: int = 30
    required_permission: str | None = None


@dataclass(frozen=True)
class ToolResult:
    tool_name: str
    output: Any
    duration_ms: int


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        if spec.name in self._tools:
            raise ValueError(f"Tool already registered: {spec.name}")
        self._tools[spec.name] = spec

    def list_tools(self) -> list[ToolSpec]:
        return list(self._tools.values())

    def get(self, name: str) -> ToolSpec:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise ToolNotFoundError(name) from exc

    def execute(
        self,
        name: str,
        /,
        *,
        permissions: set[str] | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        spec = self.get(name)
        if spec.required_permission and spec.required_permission not in (permissions or set()):
            raise ToolPermissionError(
                f"Missing permission: {spec.required_permission}"
            )
        started = perf_counter()
        try:
            output = spec.handler(**kwargs)
        except Exception as exc:
            raise ToolExecutionError(f"{name} failed: {exc}") from exc
        duration_ms = int((perf_counter() - started) * 1000)
        return ToolResult(tool_name=name, output=output, duration_ms=duration_ms)
