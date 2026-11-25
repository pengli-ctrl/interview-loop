"""测试模块，覆盖管理控制台相关行为和回归场景。"""
from pathlib import Path

from streamlit.testing.v1 import AppTest

import interview_loop.config as config
from interview_loop.admin.control_plane import (
    format_local_time,
    format_quality_thresholds,
    format_quota_snapshot,
    format_rag_thresholds,
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
    """验证控制台摘要行。

    Args:
        tmp_path: `tmp_path` 输入参数，类型为 未标注。

    """
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
    """准备测试应用和临时数据库。

    Args:
        monkeypatch: `monkeypatch` 输入参数，类型为 未标注。
        tmp_path: `tmp_path` 输入参数，类型为 未标注。

    Returns:
        函数处理结果，类型为 未标注。

    """
    monkeypatch.setattr(config, "SAVE_DIR", tmp_path / "sessions")
    monkeypatch.setattr(config, "RECORD_DIR", tmp_path / "records")
    monkeypatch.setattr(config, "GLOBAL_STATS_PATH", tmp_path / "weak_stats.json")
    db_path = tmp_path / "admin.db"
    monkeypatch.setenv("INTERVIEWLOOP_DB_PATH", str(db_path))
    return Path(__file__).resolve().parents[1] / "app.py", db_path


def test_admin_hidden_by_default_and_direct_access_redirects(monkeypatch, tmp_path):
    """验证管理台默认隐藏且直接访问会重定向。

    Args:
        monkeypatch: `monkeypatch` 输入参数，类型为 未标注。
        tmp_path: `tmp_path` 输入参数，类型为 未标注。

    """
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
    """验证管理台读取真实场景、工具、Run 和评估数据。

    Args:
        monkeypatch: `monkeypatch` 输入参数，类型为 未标注。
        tmp_path: `tmp_path` 输入参数，类型为 未标注。

    """
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


def test_admin_formatting_helpers_do_not_render_python_dicts():
    """验证管理台格式化辅助函数不输出 Python 字典。"""
    rag = format_rag_thresholds({"precision": 0.3, "recall": 0.9, "mrr": 0.9, "hit_rate": 0.9})
    quality = format_quality_thresholds({"weighted_mae": 0.75, "max_case_mae": 1.0})
    quota = format_quota_snapshot({"used_tokens": 10, "max_tokens": 100, "used_cost": 0.12, "max_cost": 5.0})
    assert "Precision \u2265 0.30" in rag
    assert "Hit Rate \u2265 0.90" in rag
    assert "MAE \u2264 0.75" in quality
    assert "10 / 100 Token" in quota
    assert "\u00a50.1200 / \u00a55.00" in quota
    assert "{" not in rag + quality + quota


def test_admin_timestamp_is_rendered_in_china_time():
    """验证管理台时间戳按本地时间渲染。"""
    assert format_local_time("2026-11-25T12:29:28.923294+00:00") == "2026-11-25 20:29:28"
