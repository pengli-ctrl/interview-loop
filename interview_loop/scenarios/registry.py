"""场景注册表模块，负责加载场景包、按轮次查询和兼容旧配置。"""
import json
from functools import lru_cache
from pathlib import Path

from interview_loop.scenarios.models import (
    ScenarioPack,
    ScenarioSpec,
    ScenarioValidationError,
)

DEFAULT_PACK_DIR = Path(__file__).resolve().parent / "packs"


class ScenarioNotFoundError(LookupError):
    """表示场景不存在的异常。"""
    pass


class ScenarioRegistry:
    """场景注册表。"""
    def __init__(self, packs: list[ScenarioPack]) -> None:
        """初始化场景注册表。

        Args:
            packs: `packs` 输入参数，类型为 list[ScenarioPack]。

        Raises:
            ScenarioValidationError: 当输入、状态或外部依赖不满足要求时抛出 ScenarioValidationError。

        """
        if not packs:
            raise ScenarioValidationError("At least one scenario pack is required")
        self.packs = tuple(packs)
        self._by_id: dict[str, ScenarioSpec] = {}
        self._by_round: dict[str, ScenarioSpec] = {}
        for pack in self.packs:
            for scenario in pack.scenarios:
                if scenario.id in self._by_id:
                    raise ScenarioValidationError(
                        f"Duplicate scenario id: {scenario.id}"
                    )
                if scenario.interview_round in self._by_round:
                    raise ScenarioValidationError(
                        "Duplicate interview round: "
                        f"{scenario.interview_round}"
                    )
                self._by_id[scenario.id] = scenario
                self._by_round[scenario.interview_round] = scenario

    @classmethod
    def from_directory(cls, pack_dir: str | Path = DEFAULT_PACK_DIR) -> "ScenarioRegistry":
        """从目录加载场景包。

        Args:
            pack_dir: `pack_dir` 输入参数，类型为 str | Path。

        Returns:
            函数处理结果，类型为 'ScenarioRegistry'。

        Raises:
            ScenarioValidationError: 当输入、状态或外部依赖不满足要求时抛出 ScenarioValidationError。

        """
        path = Path(pack_dir)
        if not path.is_dir():
            raise ScenarioValidationError(f"Scenario pack directory not found: {path}")
        packs = []
        for pack_file in sorted(path.glob("*.json")):
            try:
                data = json.loads(pack_file.read_text(encoding="utf-8"))
                packs.append(ScenarioPack.from_dict(data))
            except (OSError, json.JSONDecodeError) as exc:
                raise ScenarioValidationError(
                    f"Unable to load scenario pack {pack_file.name}: {exc}"
                ) from exc
        if not packs:
            raise ScenarioValidationError(f"No scenario packs found in {path}")
        return cls(packs)

    def get(self, scenario_id: str) -> ScenarioSpec:
        """按 ID 获取场景。

        Args:
            scenario_id: `scenario_id` 输入参数，类型为 str。

        Returns:
            函数处理结果，类型为 ScenarioSpec。

        Raises:
            ScenarioNotFoundError: 当输入、状态或外部依赖不满足要求时抛出 ScenarioNotFoundError。

        """
        try:
            return self._by_id[scenario_id]
        except KeyError as exc:
            raise ScenarioNotFoundError(scenario_id) from exc

    def scenario_for_round(self, interview_round: str) -> ScenarioSpec:
        """按面试轮次获取场景。

        Args:
            interview_round: `interview_round` 输入参数，类型为 str。

        Returns:
            函数处理结果，类型为 ScenarioSpec。

        Raises:
            ScenarioNotFoundError: 当输入、状态或外部依赖不满足要求时抛出 ScenarioNotFoundError。

        """
        try:
            return self._by_round[interview_round]
        except KeyError as exc:
            raise ScenarioNotFoundError(interview_round) from exc

    def list_scenarios(self) -> list[ScenarioSpec]:
        """列出全部场景。

        Returns:
            函数处理结果，类型为 list[ScenarioSpec]。

        """
        return list(self._by_id.values())

    def interview_rounds(self) -> list[str]:
        """列出面试轮次。

        Returns:
            函数处理结果，类型为 list[str]。

        """
        return [scenario.interview_round for scenario in self.list_scenarios()]

    def styles(self) -> list[str]:
        """列出面试风格。

        Returns:
            函数处理结果，类型为 list[str]。

        """
        result = []
        for pack in self.packs:
            for style in pack.styles:
                if style not in result:
                    result.append(style)
        return result

    def legacy_mode_config(self) -> dict:
        """生成旧版模式配置。

        Returns:
            函数处理结果，类型为 dict。

        """
        return {
            scenario.interview_round: scenario.legacy_dict()
            for scenario in self.list_scenarios()
        }

    def catalog(self) -> list[dict]:
        """返回场景目录。

        Returns:
            函数处理结果，类型为 list[dict]。

        """
        return [scenario.to_dict() for scenario in self.list_scenarios()]


@lru_cache(maxsize=1)
def get_default_registry() -> ScenarioRegistry:
    """获取默认场景注册表。

    Returns:
        函数处理结果，类型为 ScenarioRegistry。

    """
    return ScenarioRegistry.from_directory()
