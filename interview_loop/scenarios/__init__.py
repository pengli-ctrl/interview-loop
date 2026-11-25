"""scenarios 包的初始化模块，用于声明 Python 包。"""
from interview_loop.scenarios.models import (
    RubricDimensionSpec,
    ScenarioPack,
    ScenarioSpec,
    ScenarioValidationError,
    StageSpec,
)
from interview_loop.scenarios.registry import (
    ScenarioNotFoundError,
    ScenarioRegistry,
    get_default_registry,
)

__all__ = [
    "RubricDimensionSpec",
    "ScenarioNotFoundError",
    "ScenarioPack",
    "ScenarioRegistry",
    "ScenarioSpec",
    "ScenarioValidationError",
    "StageSpec",
    "get_default_registry",
]
