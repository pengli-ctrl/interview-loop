import copy
import json
from pathlib import Path

import pytest

import interview_loop.config as config
from interview_loop.scenarios import (
    ScenarioPack,
    ScenarioRegistry,
    ScenarioValidationError,
    get_default_registry,
)


def _pack_data() -> dict:
    root = Path(__file__).resolve().parents[1]
    return json.loads(
        (root / "interview_loop" / "scenarios" / "packs" / "technical.json").read_text(
            encoding="utf-8"
        )
    )


def test_default_registry_matches_existing_interview_rounds():
    registry = get_default_registry()
    assert registry.interview_rounds() == ["技术一面", "技术二面", "技术三面", "HR面"]
    assert [scenario.id for scenario in registry.list_scenarios()] == [
        "tech_screen_1",
        "tech_screen_2",
        "tech_screen_3",
        "hr_screen",
    ]
    assert registry.legacy_mode_config() == config.MODE_CONFIG


def test_technical_scenario_preserves_stage_plan():
    scenario = get_default_registry().get("tech_screen_1")
    assert scenario.duration_minutes == 60
    assert len(scenario.stages) == 6
    assert [len(stage.question_plan) for stage in scenario.stages] == [1, 1, 2, 3, 1, 1]
    assert sum(stage.time_budget_min for stage in scenario.stages) == 60
    assert sum(item.weight for item in scenario.rubric) == pytest.approx(1.0)


def test_stage_budget_must_match_duration():
    data = _pack_data()
    data["scenarios"][0]["duration_minutes"] = 30
    with pytest.raises(ScenarioValidationError, match="stage budgets"):
        ScenarioPack.from_dict(data)


def test_empty_question_plan_is_rejected():
    data = _pack_data()
    data["scenarios"][0]["stages"][0]["question_plan"] = []
    with pytest.raises(ScenarioValidationError, match="question_plan"):
        ScenarioPack.from_dict(data)


def test_empty_stages_are_rejected():
    data = _pack_data()
    data["scenarios"][0]["stages"] = []
    with pytest.raises(ScenarioValidationError, match="stages"):
        ScenarioPack.from_dict(data)


def test_invalid_rubric_weights_are_rejected():
    data = _pack_data()
    data["scenarios"][0]["rubric"][0]["weight"] = 0.1
    with pytest.raises(ScenarioValidationError, match="sum to 1.0"):
        ScenarioPack.from_dict(data)


def test_duplicate_scenario_ids_are_rejected():
    data = _pack_data()
    pack = ScenarioPack.from_dict(data)
    with pytest.raises(ScenarioValidationError, match="Duplicate scenario id"):
        ScenarioRegistry([pack, pack])


def test_registry_rejects_duplicate_round_names():
    data = _pack_data()
    duplicate = copy.deepcopy(data)
    duplicate["scenarios"][0]["id"] = "another_tech_screen"
    packs = [ScenarioPack.from_dict(data), ScenarioPack.from_dict(duplicate)]
    with pytest.raises(ScenarioValidationError, match="Duplicate interview round"):
        ScenarioRegistry(packs)
