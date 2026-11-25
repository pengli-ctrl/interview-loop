from pathlib import Path

from streamlit.testing.v1 import AppTest

import interview_loop.config as config
from interview_loop.evaluation.replay import replay_agent_run


def test_demo_product_shell_and_complete_interview(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DEMO_MODE", True)
    monkeypatch.setattr(config, "SAVE_DIR", tmp_path / "sessions")
    monkeypatch.setattr(config, "RECORD_DIR", tmp_path / "records")
    monkeypatch.setattr(config, "GLOBAL_STATS_PATH", tmp_path / "weak_stats.json")

    import interview_loop.services.llm as llm
    import interview_loop.services.tts as tts

    monkeypatch.setattr(llm, "DEMO_MODE", True)
    monkeypatch.setattr(tts, "DEMO_MODE", True)

    app_path = Path(__file__).resolve().parents[1] / "app.py"
    at = AppTest.from_file(str(app_path), default_timeout=30).run()
    assert not at.exception
    assert at.session_state["current_view"] == "dashboard"

    navigation = at.get_by_key(f"main_navigation_{at.session_state['nav_version']}")
    assert navigation.options == [
        "工作台",
        "开始面试",
        "面试室",
        "复盘报告",
        "成长记录",
    ]
    navigation.set_value("开始面试").run()
    assert not at.exception
    assert at.session_state["current_view"] == "setup"

    at.button(key="setup_next").click().run()
    assert not at.exception
    assert at.session_state["setup_step"] == 2
    at.text_area(key="job_description_input").set_value(
        "负责 Python FastAPI Redis RAG 服务开发，要求具备可观测性和分布式系统经验。"
    )
    at.button(key="setup_next").click().run()
    assert not at.exception
    assert at.session_state["setup_step"] == 3
    assert at.session_state["job_match"].match_score == 0
    assert at.session_state["job_match"].missing_skills

    at.get_by_key("consent_checkbox").check().run()
    assert not at.exception
    at.button(key="start_interview").click().run(timeout=30)
    assert not at.exception
    assert at.session_state["current_view"] == "interview"
    assert at.session_state["current_question"]
    assert at.session_state["agent_run"].metadata["scenario_id"] == "tech_screen_1"
    assert at.session_state["agent_run"].metadata["job_match_score"] == 0
    assert at.session_state["agent_run"].metadata["missing_skills"]
    assert at.session_state["model_budget"].used_tokens > 0

    events = at.session_state["agent_run"].events
    assert any(event.event_type == "model.call" for event in events)
    assert any(event.event_type == "question.generated" for event in events)

    answer_mode = at.get_by_key("answer_input_mode")
    answer_mode.set_value(answer_mode.options[1]).run()
    assert not at.exception

    at.text_area(key="text_answer").set_value("short answer")
    at.button(key="submit_text_answer").click().run(timeout=30)
    assert not at.exception
    assert not at.error, [item.value for item in at.error]
    assert at.session_state["current_stage_idx"] == 1

    for _ in range(12):
        if at.session_state["current_stage_idx"] >= 6:
            break
        at.text_area(key="text_answer").set_value("short answer")
        at.button(key="submit_text_answer").click().run(timeout=30)
        assert not at.exception
        assert not at.error, [item.value for item in at.error]

    assert at.session_state["current_stage_idx"] == 6

    events = at.session_state["agent_run"].events
    event_types = [event.event_type for event in events]
    assert event_types.count("stage.transition") == 6
    question_events = [
        event for event in events if event.event_type == "question.generated"
    ]
    assert question_events[0].payload["stage_index"] == 0
    assert "main_index" in question_events[0].payload

    at.button(key="finish_interview").click().run(timeout=30)
    assert not at.exception
    assert not at.error, [item.value for item in at.error]
    assert at.session_state["current_view"] == "report"
    assert at.session_state["feedback"]
    finished_events = at.session_state["agent_run"].events
    finished_types = [event.event_type for event in finished_events]
    assert "evaluation.completed" in finished_types
    assert "record.exported" in finished_types
    assert finished_types[-1] == "run.completed"
    assert list((tmp_path / "sessions").glob("*.json"))
    assert list((tmp_path / "records").glob("*.md"))

    replay = replay_agent_run(at.session_state["agent_run"].to_dict())
    assert replay.completed
    assert replay.evaluation_completed
    assert replay.record_exported
    assert replay.final_stage == 6

    navigation = at.get_by_key(f"main_navigation_{at.session_state['nav_version']}")
    navigation.set_value("成长记录").run()
    assert not at.exception
    assert at.session_state["current_view"] == "growth"
