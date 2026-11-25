import json
import time
from pathlib import Path

from streamlit.testing.v1 import AppTest

import interview_loop.config as config
from interview_loop.evaluation.interview_report import InterviewReport
from interview_loop.evaluation.replay import replay_agent_run
from interview_loop.platform.run_repository import SQLiteAgentRunRepository
from interview_loop.storage.draft_store import save_interview_draft


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
    retention = at.get_by_key("retention_policy_select")
    assert retention.options == [
        "临时（1 天）",
        "标准（30 天）",
        "延长（365 天）",
    ]
    retention.set_value("延长（365 天）").run()
    assert at.session_state["retention_policy"] == "extended"

    at.get_by_key("consent_checkbox").check().run()
    assert not at.exception
    at.button(key="start_interview").click().run(timeout=30)
    assert not at.exception
    assert at.session_state["current_view"] == "interview"
    assert at.session_state["current_question"]
    assert at.session_state["start_time"] is not None
    assert at.session_state["stage_started_at"] is not None
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

    import interview_loop.services.llm as llm_service

    original_demo_response = llm_service.build_demo_llm_response

    def fail_next_question(system_prompt, user_msg):
        raise RuntimeError("next question failed")

    monkeypatch.setattr(llm_service, "build_demo_llm_response", fail_next_question)
    at.text_area(key="text_answer").set_value("first attempt")
    at.button(key="submit_text_answer").click().run(timeout=30)
    assert not at.exception
    assert at.error
    assert at.session_state["messages"] == []
    assert at.session_state["current_stage_idx"] == 0

    monkeypatch.setattr(llm_service, "build_demo_llm_response", original_demo_response)
    at.text_area(key="text_answer").set_value("short answer")
    at.button(key="submit_text_answer").click().run(timeout=30)
    assert not at.exception
    assert not at.error, [item.value for item in at.error]
    assert len(at.session_state["messages"]) == 2
    assert at.session_state["current_stage_idx"] == 1
    assert at.session_state["stage_started_at"] >= at.session_state["start_time"]
    draft_files = list((tmp_path / "sessions" / "drafts").glob("*.json"))
    assert len(draft_files) == 1

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
    at.button(key="confirm_finish_interview").click().run(timeout=30)
    at.run(timeout=30)
    assert not at.exception
    assert not at.error, [item.value for item in at.error]
    assert at.session_state["current_view"] == "report"
    assert at.session_state["feedback"]
    structured_report = at.session_state["structured_report"]
    assert isinstance(structured_report, InterviewReport)
    assert structured_report.overall_score > 0
    assert structured_report.source == "structure-heuristic-v1"
    assert any("表达结构参考分" in item.value for item in at.markdown)
    assert any("优先行动" in item.value for item in at.markdown)
    assert any("演示流程" in item.value for item in at.markdown)
    assert len(structured_report.dimensions) == 4
    finished_events = at.session_state["agent_run"].events
    finished_types = [event.event_type for event in finished_events]
    assert "evaluation.completed" in finished_types
    assert "record.exported" in finished_types
    assert finished_types[-1] == "run.completed"
    assert list((tmp_path / "sessions").glob("*.json"))
    assert list((tmp_path / "records").glob("*.md"))
    assert list((tmp_path / "sessions" / "drafts").glob("*.json")) == []
    persisted_run = SQLiteAgentRunRepository(tmp_path / "interview_loop.db").get(
        at.session_state["agent_run"].run_id
    )
    assert persisted_run.run_id == at.session_state["agent_run"].run_id
    assert persisted_run.events
    assert (tmp_path / "sessions" / "weak_stats.json").exists()
    assert not (tmp_path / "weak_stats.json").exists()

    replay = replay_agent_run(at.session_state["agent_run"].to_dict())
    assert replay.completed
    assert replay.evaluation_completed
    assert replay.record_exported
    assert replay.final_stage == 6

    navigation = at.get_by_key(f"main_navigation_{at.session_state['nav_version']}")
    navigation.set_value("成长记录").run()
    assert not at.exception
    assert at.session_state["current_view"] == "growth"

    navigation = at.get_by_key(f"main_navigation_{at.session_state['nav_version']}")
    navigation.set_value("开始面试").run()
    assert not at.exception
    assert at.session_state["current_view"] == "setup"
    assert at.session_state["setup_step"] == 1


def test_legacy_session_without_structured_report_opens(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DEMO_MODE", True)
    save_dir = tmp_path / "sessions"
    save_dir.mkdir()
    monkeypatch.setattr(config, "SAVE_DIR", save_dir)
    monkeypatch.setattr(config, "RECORD_DIR", tmp_path / "records")
    monkeypatch.setattr(config, "GLOBAL_STATS_PATH", tmp_path / "weak_stats.json")
    legacy = {
        "session_id": "legacy_session",
        "started_at": "2026-01-01_10-00-00",
        "time": "2026-01-01 10:00:00",
        "completed_at": "2026-01-01 10:30:00",
        "mode": "技术一面",
        "interview_type": "闯关全真面试",
        "style": "温和",
        "duration_seconds": 1800,
        "messages": [
            {"role": "interviewer", "content": "旧问题"},
            {"role": "candidate", "content": "旧回答"},
        ],
        "feedback": "旧版复盘内容",
        "tags": ["RAG"],
    }
    (save_dir / "legacy_session.json").write_text(
        json.dumps(legacy, ensure_ascii=False),
        encoding="utf-8",
    )

    app_path = Path(__file__).resolve().parents[1] / "app.py"
    at = AppTest.from_file(str(app_path), default_timeout=30).run()
    navigation = at.get_by_key(f"main_navigation_{at.session_state['nav_version']}")
    navigation.set_value("成长记录").run()
    assert not at.exception
    at.button(key="history_legacy_session").click().run()
    assert not at.exception
    assert at.session_state["current_view"] == "report"
    assert any("旧版" in item.value for item in at.info)
    assert any("30分0秒" in item.value for item in at.markdown)


def test_unfinished_interview_draft_can_be_restored(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DEMO_MODE", True)
    save_dir = tmp_path / "sessions"
    save_dir.mkdir()
    monkeypatch.setattr(config, "SAVE_DIR", save_dir)
    monkeypatch.setattr(config, "RECORD_DIR", tmp_path / "records")
    monkeypatch.setattr(config, "GLOBAL_STATS_PATH", tmp_path / "weak_stats.json")
    save_interview_draft(
        save_dir,
        {
            "version": 1,
            "session_id": "session_restore",
            "mode": "技术一面",
            "interview_type": "闯关全真面试",
            "style": "温和",
            "current_stage_idx": 1,
            "stage_main_index": 0,
            "stage_followup_count": 0,
            "messages": [
                {"role": "interviewer", "content": "旧问题"},
                {"role": "candidate", "content": "旧回答"},
            ],
            "current_question": "当前问题",
            "started_at": "2026-11-25_10-00-00",
            "start_time": time.time() - 120,
            "job_description": "",
            "job_match": None,
            "resume_text": "",
            "tenant_id": "local",
            "user_id": "local",
            "consent_granted": True,
            "consent_at": "2026-11-25 10:00:00",
            "retention_policy": "standard",
            "updated_at": "2026-11-25 10:02:00",
        },
    )

    app_path = Path(__file__).resolve().parents[1] / "app.py"
    at = AppTest.from_file(str(app_path), default_timeout=30).run()
    assert not at.exception
    assert at.session_state["pending_draft"]["session_id"] == "session_restore"
    at.button(key="restore_interview_draft").click().run()
    assert not at.exception
    assert at.session_state["current_view"] == "interview"
    assert at.session_state["current_question"] == "当前问题"
    assert len(at.session_state["messages"]) == 2
    assert at.session_state["current_stage_idx"] == 1

    refreshed = AppTest.from_file(str(app_path), default_timeout=30).run()
    assert not refreshed.exception
    restored = refreshed.session_state["pending_draft"]
    assert restored["session_id"] == "session_restore"
    assert len(restored["messages"]) == 2
    assert restored["current_question"] == "当前问题"


def test_new_interview_reset_clears_stale_resume_state(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DEMO_MODE", True)
    monkeypatch.setattr(config, "SAVE_DIR", tmp_path / "sessions")
    monkeypatch.setattr(config, "RECORD_DIR", tmp_path / "records")
    monkeypatch.setattr(config, "GLOBAL_STATS_PATH", tmp_path / "weak_stats.json")
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    at = AppTest.from_file(str(app_path), default_timeout=30).run()
    at.session_state["resume_text"] = "旧简历"
    at.session_state["resume_retriever"] = object()
    at.session_state["resume_signature"] = "old-signature"
    at.session_state["resume_name"] = "old.txt"
    at.session_state["resume_chars"] = 3
    at.session_state["resume_rag_mode"] = "BM25"
    at.session_state["job_match"] = object()
    at.run()
    at.button(key="sidebar_new_interview").click().run()
    assert not at.exception
    assert at.session_state["resume_text"] == ""
    assert at.session_state["resume_retriever"] is None
    assert at.session_state["resume_signature"] is None
    assert at.session_state["resume_name"] is None
    assert at.session_state["resume_chars"] == 0
    assert at.session_state["resume_rag_mode"] is None
    assert at.session_state["job_match"] is None
    assert at.session_state["resume_upload_version"] == 1


def test_dashboard_uses_empty_state_without_zero_metrics(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DEMO_MODE", True)
    monkeypatch.setattr(config, "SAVE_DIR", tmp_path / "sessions")
    monkeypatch.setattr(config, "RECORD_DIR", tmp_path / "records")
    monkeypatch.setattr(config, "GLOBAL_STATS_PATH", tmp_path / "weak_stats.json")
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    at = AppTest.from_file(str(app_path), default_timeout=30).run()
    assert not at.exception
    text_values = [item.value for item in at.markdown] + [item.value for item in at.caption]
    assert any("还没有训练记录" in value for value in text_values)
    assert not any(item.label == "历史训练" for item in at.metric)


def test_growth_single_record_shows_next_step_instead_of_empty_chart(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DEMO_MODE", True)
    save_dir = tmp_path / "sessions"
    save_dir.mkdir()
    monkeypatch.setattr(config, "SAVE_DIR", save_dir)
    monkeypatch.setattr(config, "RECORD_DIR", tmp_path / "records")
    monkeypatch.setattr(config, "GLOBAL_STATS_PATH", tmp_path / "weak_stats.json")
    record = {
        "session_id": "one_training",
        "time": "2026-11-25 10:00:00",
        "started_at": "2026-11-25_10-00-00",
        "completed_at": "2026-11-25 10:20:00",
        "duration_seconds": 1200,
        "mode": "技术一面",
        "interview_type": "闯关全真面试",
        "style": "温和",
        "messages": [],
        "feedback": "复盘",
        "tags": ["RAG"],
        "structured_report": {"overall_score": 6.5, "dimensions": []},
    }
    (save_dir / "one_training.json").write_text(
        json.dumps(record, ensure_ascii=False),
        encoding="utf-8",
    )
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    at = AppTest.from_file(str(app_path), default_timeout=30).run()
    navigation = at.get_by_key(f"main_navigation_{at.session_state['nav_version']}")
    navigation.set_value("成长记录").run()
    assert not at.exception
    assert any(item.label == "当前表达结构参考分" for item in at.metric)
    assert at.get("progress")
    assert at.get("progress")[0].value == 65
    assert at.get("download_button")
    at.button(key="delete_one_training").click().run()
    assert (save_dir / "one_training.json").exists()
    assert any("无法恢复" in item.value for item in at.warning)
    at.button(key="confirm_delete_one_training").click().run()
    assert not (save_dir / "one_training.json").exists()


def test_legacy_weak_stats_migrates_to_tenant_storage(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DEMO_MODE", True)
    save_dir = tmp_path / "sessions"
    save_dir.mkdir()
    monkeypatch.setattr(config, "SAVE_DIR", save_dir)
    monkeypatch.setattr(config, "RECORD_DIR", tmp_path / "records")
    legacy_path = tmp_path / "weak_stats_mode.json"
    legacy_path.write_text(
        json.dumps({"技术一面": {"RAG": 3}}, ensure_ascii=False),
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "GLOBAL_STATS_PATH", legacy_path)
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    at = AppTest.from_file(str(app_path), default_timeout=30).run()
    assert not at.exception
    migrated = save_dir / "weak_stats.json"
    assert migrated.exists()
    assert json.loads(migrated.read_text(encoding="utf-8"))["技术一面"]["RAG"] == 3
