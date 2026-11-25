from pathlib import Path

from streamlit.testing.v1 import AppTest

import interview_loop.config as config
from interview_loop.admin.control_plane import (
    model_profile_rows,
    quality_metrics,
    recent_run_rows,
    scenario_rows,
    tool_rows,
)
from interview_loop.platform.agent_run import AgentRun
from interview_loop.platform.builtin_tools import build_default_tool_registry
from interview_loop.platform.model_gateway import ModelGateway
from interview_loop.platform.run_repository import SQLiteAgentRunRepository
from interview_loop.scenarios import get_default_registry


def test_control_plane_summary_rows(tmp_path):
    registry = get_default_registry()
    assert len(scenario_rows(registry)) == 4
    assert len(tool_rows(build_default_tool_registry())) >= 5
    assert len(model_profile_rows(ModelGateway(completer=lambda *_: "ok"))) == 3
    quality = quality_metrics(Path("datasets/quality_golden.json"))
    assert quality["case_count"] >= 3
    assert quality["passed"] is True

    repository = SQLiteAgentRunRepository(tmp_path / "runs.db")
    run = AgentRun(tenant_id="tenant-a", user_id="user-a", consent_granted=True)
    run.start()
    run.record_event("answer.received", "interview.answer", {"length": 10})
    repository.create(run)
    rows = recent_run_rows(repository)
    assert rows[0]["Run"] == run.run_id
    assert rows[0]["事件数"] == 2


def _prepare_app(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "SAVE_DIR", tmp_path / "sessions")
    monkeypatch.setattr(config, "RECORD_DIR", tmp_path / "records")
    monkeypatch.setattr(config, "GLOBAL_STATS_PATH", tmp_path / "weak_stats.json")
    db_path = tmp_path / "admin.db"
    monkeypatch.setenv("INTERVIEWLOOP_DB_PATH", str(db_path))
    return Path(__file__).resolve().parents[1] / "app.py", db_path


def test_admin_hidden_by_default_and_direct_access_redirects(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "ADMIN_MODE", False)
    app_path, _ = _prepare_app(monkeypatch, tmp_path)
    at = AppTest.from_file(str(app_path), default_timeout=30).run()
    navigation = at.get_by_key(f"main_navigation_{at.session_state['nav_version']}")
    assert "管理控制台" not in navigation.options

    at.session_state["current_view"] = "admin"
    at.run()
    assert not at.exception
    assert at.session_state["current_view"] == "dashboard"


def test_admin_console_reads_real_scenario_tool_run_and_eval_data(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "ADMIN_MODE", True)
    app_path, db_path = _prepare_app(monkeypatch, tmp_path)
    repository = SQLiteAgentRunRepository(db_path)
    run = AgentRun(tenant_id="tenant-admin", user_id="admin", consent_granted=True)
    run.start("admin.seed")
    run.record_event("model.call", "model.review", {"latency_ms": 100})
    repository.create(run)

    at = AppTest.from_file(str(app_path), default_timeout=30).run()
    navigation = at.get_by_key(f"main_navigation_{at.session_state['nav_version']}")
    assert navigation.options[-1] == "管理控制台"
    navigation.set_value("管理控制台").run(timeout=30)
    assert not at.exception
    assert at.session_state["current_view"] == "admin"
    assert any(header.value == "平台控制台" for header in at.header)
    assert len(at.dataframe) >= 5
    assert at.selectbox(key="admin_run_selector").value == run.run_id
