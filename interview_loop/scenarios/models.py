from dataclasses import dataclass
from typing import Any


class ScenarioValidationError(ValueError):
    pass


def _require_text(value: Any, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ScenarioValidationError(f"{field} must not be empty")
    return text


def _text_list(value: Any, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise ScenarioValidationError(f"{field} must be a non-empty list")
    result = tuple(_require_text(item, field) for item in value)
    if not result:
        raise ScenarioValidationError(f"{field} must not be empty")
    return result


@dataclass(frozen=True)
class RubricDimensionSpec:
    name: str
    weight: float

    @classmethod
    def from_dict(cls, data: dict) -> "RubricDimensionSpec":
        name = _require_text(data.get("name"), "rubric.name")
        try:
            weight = float(data.get("weight"))
        except (TypeError, ValueError) as exc:
            raise ScenarioValidationError(
                f"rubric weight for {name} must be numeric"
            ) from exc
        if weight <= 0 or weight > 1:
            raise ScenarioValidationError(
                f"rubric weight for {name} must be between 0 and 1"
            )
        return cls(name=name, weight=weight)

    def to_dict(self) -> dict:
        return {"name": self.name, "weight": self.weight}


@dataclass(frozen=True)
class StageSpec:
    name: str
    description: str
    pool: tuple[str, ...]
    question_plan: tuple[str, ...]
    max_followups: int
    time_budget_min: int

    @classmethod
    def from_dict(cls, data: dict) -> "StageSpec":
        name = _require_text(data.get("name"), "stage.name")
        description = _require_text(
            data.get("desc", data.get("description")),
            f"stage {name}.description",
        )
        pool = _text_list(data.get("pool"), f"stage {name}.pool")
        question_plan = _text_list(
            data.get("question_plan"),
            f"stage {name}.question_plan",
        )
        try:
            max_followups = int(data.get("max_followups", 0))
        except (TypeError, ValueError) as exc:
            raise ScenarioValidationError(
                f"stage {name}.max_followups must be an integer"
            ) from exc
        if max_followups < 0:
            raise ScenarioValidationError(
                f"stage {name}.max_followups must be non-negative"
            )
        try:
            time_budget_min = int(data.get("time_budget_min", 0))
        except (TypeError, ValueError) as exc:
            raise ScenarioValidationError(
                f"stage {name}.time_budget_min must be an integer"
            ) from exc
        if time_budget_min <= 0:
            raise ScenarioValidationError(
                f"stage {name}.time_budget_min must be positive"
            )
        return cls(
            name=name,
            description=description,
            pool=pool,
            question_plan=question_plan,
            max_followups=max_followups,
            time_budget_min=time_budget_min,
        )

    def legacy_dict(self) -> dict:
        return {
            "name": self.name,
            "desc": self.description,
            "pool": list(self.pool),
            "question_plan": list(self.question_plan),
            "max_followups": self.max_followups,
            "time_budget_min": self.time_budget_min,
        }

    def to_dict(self) -> dict:
        return self.legacy_dict()


@dataclass(frozen=True)
class ScenarioSpec:
    id: str
    job_family: str
    role: str
    seniority: str
    language: str
    interview_round: str
    description: str
    tags: tuple[str, ...]
    default_style: str
    duration_minutes: int
    styles: tuple[str, ...]
    stages: tuple[StageSpec, ...]
    rubric: tuple[RubricDimensionSpec, ...]

    @classmethod
    def from_dict(cls, data: dict, pack: dict) -> "ScenarioSpec":
        scenario_id = _require_text(data.get("id"), "scenario.id")
        interview_round = _require_text(
            data.get("interview_round"),
            f"scenario {scenario_id}.interview_round",
        )
        description = _require_text(
            data.get("description"),
            f"scenario {scenario_id}.description",
        )
        tags = _text_list(data.get("tags"), f"scenario {scenario_id}.tags")
        styles = _text_list(pack.get("styles"), "pack.styles")
        default_style = _require_text(
            data.get("default_style"),
            f"scenario {scenario_id}.default_style",
        )
        if default_style not in styles:
            raise ScenarioValidationError(
                f"scenario {scenario_id}.default_style is not in pack.styles"
            )
        try:
            duration_minutes = int(data.get("duration_minutes", 60))
        except (TypeError, ValueError) as exc:
            raise ScenarioValidationError(
                f"scenario {scenario_id}.duration_minutes must be an integer"
            ) from exc
        if duration_minutes <= 0:
            raise ScenarioValidationError(
                f"scenario {scenario_id}.duration_minutes must be positive"
            )
        raw_stages = data.get("stages")
        if not isinstance(raw_stages, list) or not raw_stages:
            raise ScenarioValidationError(
                f"scenario {scenario_id}.stages must be a non-empty list"
            )
        stages = tuple(StageSpec.from_dict(item) for item in raw_stages)
        stage_names = [stage.name for stage in stages]
        if len(stage_names) != len(set(stage_names)):
            raise ScenarioValidationError(
                f"scenario {scenario_id} has duplicate stage names"
            )
        total_stage_minutes = sum(stage.time_budget_min for stage in stages)
        if total_stage_minutes != duration_minutes:
            raise ScenarioValidationError(
                f"scenario {scenario_id} stage budgets sum to {total_stage_minutes}, "
                f"expected {duration_minutes}"
            )
        raw_rubric = data.get("rubric")
        if not isinstance(raw_rubric, list) or not raw_rubric:
            raise ScenarioValidationError(
                f"scenario {scenario_id}.rubric must be a non-empty list"
            )
        rubric = tuple(RubricDimensionSpec.from_dict(item) for item in raw_rubric)
        rubric_names = [item.name for item in rubric]
        if len(rubric_names) != len(set(rubric_names)):
            raise ScenarioValidationError(
                f"scenario {scenario_id} has duplicate rubric dimensions"
            )
        if abs(sum(item.weight for item in rubric) - 1.0) > 0.001:
            raise ScenarioValidationError(
                f"scenario {scenario_id} rubric weights must sum to 1.0"
            )
        return cls(
            id=scenario_id,
            job_family=_require_text(pack.get("job_family"), "pack.job_family"),
            role=_require_text(pack.get("role"), "pack.role"),
            seniority=_require_text(pack.get("seniority"), "pack.seniority"),
            language=_require_text(pack.get("language"), "pack.language"),
            interview_round=interview_round,
            description=description,
            tags=tags,
            default_style=default_style,
            duration_minutes=duration_minutes,
            styles=styles,
            stages=stages,
            rubric=rubric,
        )

    def legacy_dict(self) -> dict:
        return {
            "desc": self.description,
            "tags": list(self.tags),
            "default_style": self.default_style,
            "stage_list": [stage.legacy_dict() for stage in self.stages],
        }

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "job_family": self.job_family,
            "role": self.role,
            "seniority": self.seniority,
            "language": self.language,
            "interview_round": self.interview_round,
            "description": self.description,
            "tags": list(self.tags),
            "default_style": self.default_style,
            "duration_minutes": self.duration_minutes,
            "styles": list(self.styles),
            "stage_count": len(self.stages),
            "question_count": sum(len(stage.question_plan) for stage in self.stages),
            "stages": [stage.to_dict() for stage in self.stages],
            "rubric": [item.to_dict() for item in self.rubric],
        }


@dataclass(frozen=True)
class ScenarioPack:
    schema_version: str
    job_family: str
    role: str
    seniority: str
    language: str
    styles: tuple[str, ...]
    scenarios: tuple[ScenarioSpec, ...]

    @classmethod
    def from_dict(cls, data: dict) -> "ScenarioPack":
        schema_version = _require_text(data.get("schema_version"), "schema_version")
        if schema_version != "1.0":
            raise ScenarioValidationError(
                f"unsupported scenario schema version: {schema_version}"
            )
        raw_scenarios = data.get("scenarios")
        if not isinstance(raw_scenarios, list) or not raw_scenarios:
            raise ScenarioValidationError("pack.scenarios must be a non-empty list")
        styles = _text_list(data.get("styles"), "pack.styles")
        scenarios = tuple(ScenarioSpec.from_dict(item, data) for item in raw_scenarios)
        return cls(
            schema_version=schema_version,
            job_family=_require_text(data.get("job_family"), "pack.job_family"),
            role=_require_text(data.get("role"), "pack.role"),
            seniority=_require_text(data.get("seniority"), "pack.seniority"),
            language=_require_text(data.get("language"), "pack.language"),
            styles=styles,
            scenarios=scenarios,
        )
