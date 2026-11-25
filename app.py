"""InterviewLoop 应用入口与业务编排模块，负责 Streamlit 会话状态、页面回调、持久化和外部服务装配。"""
import json
import os
import time
from pathlib import Path

import streamlit as st

st.set_page_config(
    page_title="InterviewLoop",
    page_icon=":material/psychology_alt:",
    layout="wide",
)

from interview_loop.config import (
    ADMIN_MODE,
    BASE_DIR,
    DEMO_MODE,
    GLOBAL_STATS_PATH,
    MODE_CONFIG,
    MODE_LIST,
    RECORD_DIR,
    SAVE_DIR,
    SCENARIO_REGISTRY,
)
from interview_loop.core.flow import (
    FlowAction,
    decide_next_step,
    is_explicit_end_request,
)
from interview_loop.core.job_match import (
    JobMatchReport,
    build_job_context,
    load_default_skill_catalog,
)
from interview_loop.core.question_engine import (
    build_repair_prompt,
    build_similarity_fallback,
    build_stage_question_prompt,
    questions_too_similar,
)
from interview_loop.core.review import (
    build_review_prompt,
    build_tag_prompt,
    parse_tags,
    strip_numeric_scores,
)
from interview_loop.evaluation.interview_report import (
    InterviewReport,
    build_interview_report,
)
from interview_loop.evaluation.rag_benchmark import evaluate_default_rag
from interview_loop.export.markdown import (
    build_markdown_record,
    safe_filename_part,
)
from interview_loop.platform.agent_run import AgentRun, RunStatus
from interview_loop.platform.builtin_tools import build_default_tool_registry
from interview_loop.platform.model_gateway import (
    ModelGateway,
    default_tenant_quota_store,
    default_usage_budget,
)
from interview_loop.platform.run_repository import SQLiteAgentRunRepository
from interview_loop.rag.retriever import build_rag, query_resume
from interview_loop.services.tts import text2audio
from interview_loop.storage.draft_store import (
    delete_interview_draft,
    latest_interview_draft,
    save_interview_draft,
)
from interview_loop.storage.session_store import (
    build_session_data,
    new_session_id,
    save_session_json,
)
from interview_loop.storage.session_store import (
    list_session_files as _list_session_files,
)
from interview_loop.storage.stats_store import load_stats, save_stats
from interview_loop.storage.tenant_paths import tenant_scoped_dir
from interview_loop.ui.admin_view import render_admin_view
from interview_loop.ui.components import (
    inject_ui_css,
)
from interview_loop.ui.dashboard_view import render_dashboard_view
from interview_loop.ui.growth_view import render_growth_view
from interview_loop.ui.interview_view import render_interview_view
from interview_loop.ui.report_view import render_report_view
from interview_loop.ui.setup_view import render_setup_view

SKILL_CATALOG = load_default_skill_catalog()
TENANT_QUOTA_STORE = default_tenant_quota_store()
MODEL_GATEWAY = ModelGateway(tenant_quota_store=TENANT_QUOTA_STORE)
TOOL_REGISTRY = build_default_tool_registry()

inject_ui_css()


def record_model_call(result, node: str) -> None:
    """把一次模型调用记录为 AgentRun 事件。

    Args:
        result: `result` 输入参数，类型为 未标注。
        node: `node` 输入参数，类型为 str。

    """
    agent_run = st.session_state.get("agent_run")
    if agent_run is None:
        return
    budget = st.session_state.get("model_budget")
    agent_run.record_event(
        "model.call",
        node,
        {
            "task": result.task,
            "provider": result.provider,
            "model": result.model,
            "prompt_version": result.prompt_version,
            "latency_ms": result.latency_ms,
            "estimated_input_tokens": result.estimated_input_tokens,
            "estimated_output_tokens": result.estimated_output_tokens,
            "estimated_cost": result.estimated_cost,
            "attempts": result.attempts,
            "tenant_id": result.tenant_id,
            "budget_used_tokens": budget.used_tokens if budget else None,
            "budget_used_cost": round(budget.used_cost, 6) if budget else None,
        },
    )


def record_run_error(error: Exception | str, node: str) -> None:
    """把运行错误记录为 AgentRun 事件。

    Args:
        error: `error` 输入参数，类型为 Exception | str。
        node: `node` 输入参数，类型为 str。

    """
    agent_run = st.session_state.get("agent_run")
    if agent_run is None:
        return
    agent_run.record_event("run.error", node, {"error": str(error)[:500]})


def current_job_context() -> str:
    """读取当前 JD/简历匹配上下文。

    Returns:
        函数处理结果，类型为 str。

    """
    report = st.session_state.get("job_match")
    return build_job_context(report) if isinstance(report, JobMatchReport) else ""


def record_question_generated(
    question: str,
    mode_cfg: dict,
    stage_idx: int,
    main_index: int,
    followup_index: int,
) -> None:
    """记录生成的问题及其阶段位置。

    Args:
        question: `question` 输入参数，类型为 str。
        mode_cfg: `mode_cfg` 输入参数，类型为 dict。
        stage_idx: `stage_idx` 输入参数，类型为 int。
        main_index: `main_index` 输入参数，类型为 int。
        followup_index: `followup_index` 输入参数，类型为 int。

    """
    agent_run = st.session_state.get("agent_run")
    if agent_run is None:
        return
    stages = mode_cfg["stage_list"]
    stage_name = stages[stage_idx]["name"] if stage_idx < len(stages) else "complete"
    agent_run.record_event(
        "question.generated",
        "interview.question",
        {
            "question": question,
            "stage_index": stage_idx,
            "stage_name": stage_name,
            "main_index": main_index,
            "followup_index": followup_index,
        },
    )


def record_stage_transition(mode_cfg: dict, from_index: int, to_index: int) -> None:
    """记录阶段切换事件。

    Args:
        mode_cfg: `mode_cfg` 输入参数，类型为 dict。
        from_index: `from_index` 输入参数，类型为 int。
        to_index: `to_index` 输入参数，类型为 int。

    """
    agent_run = st.session_state.get("agent_run")
    if agent_run is None:
        return
    stages = mode_cfg["stage_list"]
    from_name = stages[from_index]["name"] if from_index < len(stages) else "complete"
    to_name = stages[to_index]["name"] if to_index < len(stages) else "complete"
    agent_run.record_event(
        "stage.transition",
        "interview.stage",
        {
            "from_index": from_index,
            "from_stage": from_name,
            "to_index": to_index,
            "to_stage": to_name,
        },
    )


# ===================== 持久化、草稿与初始化 =====================
def current_tenant_id() -> str:
    """返回当前租户 ID，默认 local。

    Returns:
        函数处理结果，类型为 str。

    """
    return st.session_state.get("tenant_id", "local")


def tenant_save_dir() -> Path:
    """返回并创建当前租户的会话目录。

    Returns:
        函数处理结果，类型为 Path。

    """
    path = tenant_scoped_dir(SAVE_DIR, current_tenant_id())
    path.mkdir(parents=True, exist_ok=True)
    return path


def tenant_record_dir() -> Path:
    """返回并创建当前租户的 Markdown 记录目录。

    Returns:
        函数处理结果，类型为 Path。

    """
    path = tenant_scoped_dir(RECORD_DIR, current_tenant_id())
    path.mkdir(parents=True, exist_ok=True)
    return path


def agent_run_repository_path() -> Path:
    """返回 AgentRun SQLite 数据库路径。

    Returns:
        函数处理结果，类型为 Path。

    """
    return Path(
        os.getenv("INTERVIEWLOOP_DB_PATH", SAVE_DIR.parent / "interview_loop.db")
    )


def list_session_files() -> list[Path]:
    """列出当前租户的会话 JSON 文件。

    Returns:
        函数处理结果，类型为 list[Path]。

    """
    return _list_session_files(tenant_save_dir())


def current_draft_data() -> dict:
    """收集当前面试状态用于草稿保存。

    Returns:
        函数处理结果，类型为 dict。

    """
    job_match = st.session_state.get("job_match")
    return {
        "version": 1,
        "session_id": st.session_state.get("session_id"),
        "mode": st.session_state.get("mode"),
        "interview_type": st.session_state.get("interview_type"),
        "style": st.session_state.get("style"),
        "current_stage_idx": st.session_state.get("current_stage_idx", 0),
        "stage_main_index": st.session_state.get("stage_main_index", 0),
        "stage_followup_count": st.session_state.get("stage_followup_count", 0),
        "messages": list(st.session_state.get("messages", [])),
        "current_question": st.session_state.get("current_question", ""),
        "started_at": st.session_state.get("interview_started_at"),
        "start_time": st.session_state.get("start_time"),
        "stage_started_at": st.session_state.get("stage_started_at"),
        "timer_alert": st.session_state.get("timer_alert", False),
        "job_description": st.session_state.get("job_description", ""),
        "job_match": job_match.to_dict() if isinstance(job_match, JobMatchReport) else None,
        "resume_text": st.session_state.get("resume_text", ""),
        "resume_name": st.session_state.get("resume_name"),
        "resume_chars": st.session_state.get("resume_chars", 0),
        "resume_signature": st.session_state.get("resume_signature"),
        "resume_rag_mode": st.session_state.get("resume_rag_mode"),
        "tenant_id": current_tenant_id(),
        "user_id": st.session_state.get("user_id", "local"),
        "consent_granted": st.session_state.get("consent_granted", False),
        "consent_at": st.session_state.get("consent_at"),
        "retention_policy": st.session_state.get("retention_policy", "standard"),
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }


def save_current_draft() -> None:
    """保存当前面试草稿，未开始面试时跳过。"""
    if st.session_state.get("start_time") is None:
        return
    try:
        save_interview_draft(tenant_save_dir(), current_draft_data())
    except Exception as exc:
        record_run_error(exc, "draft.save.failed")
        st.session_state.draft_error = str(exc)


def clear_current_draft() -> None:
    """删除当前会话草稿并清空待恢复状态。"""
    session_id = st.session_state.get("session_id")
    if session_id:
        try:
            delete_interview_draft(tenant_save_dir(), session_id)
        except OSError:
            pass
    st.session_state.pending_draft = None


def tenant_stats_path() -> Path:
    """返回当前租户的薄弱统计文件路径。

    Returns:
        函数处理结果，类型为 Path。

    """
    return tenant_save_dir() / "weak_stats.json"


def save_global_weak_stats(stats: dict) -> None:
    """保存当前租户的薄弱标签统计。

    Args:
        stats: `stats` 输入参数，类型为 dict。

    """
    save_stats(tenant_stats_path(), stats)


def save_session(mode: str, messages: list, feedback: str, tags: list[str]) -> Path:
    """保存完整会话、Markdown 记录并持久化 AgentRun。

    Args:
        mode: `mode` 输入参数，类型为 str。
        messages: `messages` 输入参数，类型为 list。
        feedback: `feedback` 输入参数，类型为 str。
        tags: `tags` 输入参数，类型为 list[str]。

    Returns:
        函数处理结果，类型为 Path。

    """
    started_at = st.session_state.get("interview_started_at") or time.strftime(
        "%Y-%m-%d_%H-%M-%S"
    )
    duration_seconds = None
    if st.session_state.get("start_time") is not None:
        duration_seconds = int(max(0, time.time() - st.session_state.start_time))

    agent_run = st.session_state.get("agent_run")
    job_match = st.session_state.get("job_match")
    structured_report = st.session_state.get("structured_report")
    data = build_session_data(
        session_id=st.session_state.session_id,
        mode=mode,
        interview_type=st.session_state.interview_type,
        style=st.session_state.style,
        messages=messages,
        feedback=feedback,
        tags=tags,
        started_at=started_at,
        completed_at=time.strftime("%Y-%m-%d %H:%M:%S"),
        duration_seconds=duration_seconds,
        job_description=st.session_state.get("job_description", ""),
        job_match=job_match.to_dict() if isinstance(job_match, JobMatchReport) else None,
        structured_report=(
            structured_report.to_dict()
            if isinstance(structured_report, InterviewReport)
            else None
        ),
        tenant_id=current_tenant_id(),
        user_id=st.session_state.get("user_id", "local"),
        trace_id=agent_run.trace_id if agent_run is not None else None,
        consent_granted=st.session_state.get("consent_granted", False),
        consent_at=st.session_state.get("consent_at"),
        retention_policy=st.session_state.get("retention_policy", "standard"),
        retention_expires_at=(
            agent_run.retention_expires_at if agent_run is not None else None
        ),
    )
    markdown_path, markdown = TOOL_REGISTRY.execute(
        "record.export",
        permissions={"record:write"},
        record_dir=tenant_record_dir(),
        data=data,
    ).output
    if agent_run is not None:
        agent_run.record_event(
            "record.exported",
            "record.export",
            {
                "path": str(markdown_path),
                "markdown_chars": len(markdown),
            },
        )
        if agent_run.status is RunStatus.RUNNING:
            agent_run.complete("interview.review")
        try:
            SQLiteAgentRunRepository(agent_run_repository_path()).save(agent_run)
        except Exception as exc:
            data["agent_run_persisted"] = False
            data["agent_run_persist_error"] = str(exc)
            st.warning(f"AgentRun 写入控制面失败：{exc}")
        else:
            data["agent_run_persisted"] = True
        data["agent_run"] = agent_run.to_dict()
    data["demo_mode"] = DEMO_MODE
    budget = st.session_state.get("model_budget")
    if budget is not None:
        data["model_usage"] = budget.to_dict()
    json_path = save_session_json(tenant_save_dir(), data)
    st.session_state.report_duration_seconds = duration_seconds
    st.session_state.report_duration_is_demo = DEMO_MODE
    st.session_state.last_record_path = str(markdown_path)
    st.session_state.last_record_markdown = markdown
    st.session_state.session_list = list_session_files()
    return json_path


def load_saved_session_into_state(saved: dict, session_file: Path | None = None) -> None:
    """把历史会话加载到 Streamlit 会话状态。

    Args:
        saved: `saved` 输入参数，类型为 dict。
        session_file: `session_file` 输入参数，类型为 Path | None。

    """
    saved_mode = str(saved.get("mode") or MODE_LIST[0])
    messages = list(saved.get("messages") or [])
    feedback = saved.get("feedback")
    restored_report = saved.get("structured_report") or {}
    restored_match = saved.get("job_match") or {}
    markdown_name = "_".join(
        [
            safe_filename_part(saved.get("started_at", "未知")),
            safe_filename_part(saved.get("mode", "未知")),
            safe_filename_part(saved.get("interview_type", "未知")),
            safe_filename_part(saved.get("style", "未知")),
        ]
    ) + ".md"
    markdown_path = tenant_record_dir() / markdown_name
    markdown_content = (
        markdown_path.read_text(encoding="utf-8")
        if markdown_path.is_file()
        else build_markdown_record(saved)
    )

    st.session_state.messages = messages
    st.session_state.feedback = feedback
    st.session_state.last_tags = list(saved.get("tags") or [])
    st.session_state.structured_report = (
        InterviewReport.from_dict(restored_report) if restored_report else None
    )
    st.session_state.job_description = str(saved.get("job_description") or "")
    st.session_state.job_match = (
        JobMatchReport.from_dict(restored_match) if restored_match else None
    )
    st.session_state.mode = saved_mode
    st.session_state.interview_type = saved.get("interview_type", "闯关全真面试")
    st.session_state.style = saved.get("style", MODE_CONFIG[saved_mode]["default_style"])
    st.session_state.current_stage_idx = 0
    st.session_state.stage_main_index = 0
    st.session_state.stage_followup_count = 0
    st.session_state.current_question = ""
    st.session_state.question_audio = None
    st.session_state.question_audio_error = None
    st.session_state.start_time = None
    st.session_state.stage_started_at = None
    st.session_state.timer_alert = False
    st.session_state.report_duration_seconds = saved.get("duration_seconds")
    st.session_state.report_duration_is_demo = bool(saved.get("demo_mode", False))
    st.session_state.interview_started_at = saved.get("started_at")
    st.session_state.last_record_path = str(markdown_path)
    st.session_state.last_record_markdown = markdown_content
    st.session_state.agent_run = None
    st.session_state.model_budget = default_usage_budget()
    st.session_state.consent_granted = saved.get("consent_granted", False)
    st.session_state.consent_at = saved.get("consent_at")
    st.session_state.retention_policy = saved.get("retention_policy", "standard")
    st.session_state.session_id = new_session_id()
    st.session_state.setup_step = 1
    st.session_state.pending_draft = None


def open_latest_report() -> None:
    """加载并打开最近一次面试报告。"""
    sessions = list_session_files()
    if not sessions:
        return
    try:
        saved = json.loads(sessions[0].read_text(encoding="utf-8"))
    except Exception:
        return
    if not saved.get("feedback"):
        return
    load_saved_session_into_state(saved, sessions[0])
    set_view("report")
    st.rerun()


def enter_setup_view() -> None:
    """进入面试设置页，必要时重置到第一步。"""
    if st.session_state.get("feedback"):
        st.session_state.setup_step = 1
    st.session_state.current_view = "setup"
    st.session_state.nav_version = int(st.session_state.get("nav_version", 0)) + 1


def open_setup_view() -> None:
    """进入面试设置页并触发重跑。"""
    enter_setup_view()
    st.rerun()


# 初始化薄弱统计与 session state
def migrate_legacy_weak_stats() -> None:
    """把旧版全局薄弱统计迁移到当前租户目录。"""
    tenant_path = tenant_stats_path()
    if tenant_path.exists() or current_tenant_id() != "local":
        return
    if not GLOBAL_STATS_PATH.exists():
        return
    legacy_stats, error = load_stats(GLOBAL_STATS_PATH, MODE_LIST)
    if not error:
        save_stats(tenant_path, legacy_stats)


migrate_legacy_weak_stats()
_initial_weak_stats, _weak_stats_error = load_stats(tenant_stats_path(), MODE_LIST)
if _weak_stats_error:
    st.warning(f"薄弱统计文件损坏，已使用空统计：{_weak_stats_error}")

defaults = {
    "mode": MODE_LIST[0],
    "interview_type": "闯关全真面试",
    "current_stage_idx": 0,
    "stage_main_index": 0,
    "stage_followup_count": 0,
    "messages": [],
    "current_question": "",
    "feedback": None,
    "structured_report": None,
    "session_id": new_session_id(),
    "current_view": "dashboard",
    "nav_version": 0,
    "setup_step": 1,
    "last_tags": [],
    "resume_text": "",
    "job_description": "",
    "job_match": None,
    "tenant_id": "local",
    "user_id": "local",
    "consent_granted": False,
    "consent_at": None,
    "retention_policy": "standard",
    "resume_retriever": None,
    "resume_signature": None,
    "resume_name": None,
    "resume_chars": 0,
    "resume_error": None,
    "resume_rag_mode": None,
    "resume_upload_version": 0,
    "question_audio": None,
    "question_audio_error": None,
    "last_audio_digest": None,
    "global_weak_stats": _initial_weak_stats,
    "start_time": None,
    "stage_started_at": None,
    "timer_alert": False,
    "interview_started_at": None,
    "last_record_path": None,
    "last_record_markdown": None,
    "agent_run": None,
    "model_budget": default_usage_budget(),
    "session_list": list_session_files(),
    "draft_error": None,
    "report_duration_seconds": None,
    "report_duration_is_demo": False,
    "delete_confirm_id": None,
}
for key, value in defaults.items():
    st.session_state.setdefault(key, value)
st.session_state.setdefault("style", MODE_CONFIG[st.session_state.mode]["default_style"])
st.session_state.setdefault("pending_draft", latest_interview_draft(tenant_save_dir()))


def restore_pending_draft() -> None:
    """恢复未完成面试草稿，重建简历索引和 AgentRun。"""
    draft = st.session_state.get("pending_draft")
    if not isinstance(draft, dict):
        return
    resume_text = str(draft.get("resume_text") or "")
    retriever = None
    rag_mode = draft.get("resume_rag_mode")
    if resume_text:
        try:
            with st.spinner("正在恢复简历上下文..."):
                retriever, rag_mode = build_rag(resume_text)
        except Exception:
            retriever = None

    st.session_state.session_id = str(draft.get("session_id") or new_session_id())
    st.session_state.mode = str(draft.get("mode") or MODE_LIST[0])
    st.session_state.interview_type = str(
        draft.get("interview_type") or "闯关全真面试"
    )
    st.session_state.style = str(
        draft.get("style") or MODE_CONFIG[st.session_state.mode]["default_style"]
    )
    st.session_state.current_stage_idx = int(draft.get("current_stage_idx", 0))
    st.session_state.stage_main_index = int(draft.get("stage_main_index", 0))
    st.session_state.stage_followup_count = int(draft.get("stage_followup_count", 0))
    st.session_state.messages = list(draft.get("messages") or [])
    st.session_state.current_question = str(draft.get("current_question") or "")
    st.session_state.interview_started_at = draft.get("started_at")
    st.session_state.start_time = draft.get("start_time")
    st.session_state.stage_started_at = draft.get("stage_started_at")
    st.session_state.timer_alert = bool(draft.get("timer_alert", False))
    st.session_state.job_description = str(draft.get("job_description") or "")
    match_data = draft.get("job_match")
    st.session_state.job_match = (
        JobMatchReport.from_dict(match_data) if isinstance(match_data, dict) else None
    )
    st.session_state.resume_text = resume_text
    st.session_state.resume_retriever = retriever
    st.session_state.resume_rag_mode = rag_mode
    st.session_state.resume_name = draft.get("resume_name")
    st.session_state.resume_chars = int(draft.get("resume_chars", len(resume_text)))
    st.session_state.resume_signature = draft.get("resume_signature")
    st.session_state.resume_error = None
    st.session_state.consent_granted = bool(draft.get("consent_granted", False))
    st.session_state.consent_at = draft.get("consent_at")
    st.session_state.retention_policy = str(draft.get("retention_policy", "standard"))
    st.session_state.feedback = None
    st.session_state.structured_report = None
    st.session_state.last_tags = []
    st.session_state.report_duration_seconds = None
    st.session_state.report_duration_is_demo = False
    st.session_state.last_record_path = None
    st.session_state.last_record_markdown = None
    st.session_state.question_audio = None
    st.session_state.question_audio_error = None
    scenario = SCENARIO_REGISTRY.scenario_for_round(st.session_state.mode)
    resumed_run = AgentRun(
        tenant_id=current_tenant_id(),
        user_id=st.session_state.get("user_id", "local"),
        retention_policy=st.session_state.get("retention_policy", "standard"),
        consent_granted=st.session_state.get("consent_granted", False),
        consent_at=st.session_state.get("consent_at"),
        metadata={
            "mode": st.session_state.mode,
            "scenario_id": scenario.id,
            "interview_type": st.session_state.interview_type,
            "style": st.session_state.style,
            "resumed_from_draft": True,
        },
    )
    resumed_run.start("interview.resume")
    resumed_run.record_event(
        "draft.restored",
        "interview.draft",
        {
            "session_id": st.session_state.session_id,
            "answer_rounds": len(st.session_state.messages) // 2,
            "stage_index": st.session_state.current_stage_idx,
        },
    )
    st.session_state.agent_run = resumed_run
    st.session_state.model_budget = default_usage_budget()
    st.session_state.pending_draft = None
    save_current_draft()
    st.session_state.current_view = "interview"
    st.session_state.nav_version = int(st.session_state.get("nav_version", 0)) + 1
    st.rerun()


def discard_pending_draft() -> None:
    """删除待恢复的面试草稿。"""
    draft = st.session_state.get("pending_draft")
    if isinstance(draft, dict) and draft.get("session_id"):
        try:
            delete_interview_draft(tenant_save_dir(), str(draft["session_id"]))
        except OSError:
            pass
    st.session_state.pending_draft = None
    st.rerun()

# 面试流程版本升级时，重置旧会话状态。
if st.session_state.get("interview_flow_version") != 4:
    st.session_state.current_stage_idx = 0
    st.session_state.stage_main_index = 0
    st.session_state.stage_followup_count = 0
    st.session_state.messages = []
    st.session_state.feedback = None
    st.session_state.structured_report = None
    st.session_state.current_question = ""
    st.session_state.start_time = None
    st.session_state.stage_started_at = None
    st.session_state.interview_started_at = None
    st.session_state.report_duration_seconds = None
    st.session_state.report_duration_is_demo = False
    st.session_state.last_record_path = None
    st.session_state.last_record_markdown = None
    st.session_state.agent_run = None
    st.session_state.model_budget = default_usage_budget()
    st.session_state.consent_granted = False
    st.session_state.consent_at = None
    st.session_state.session_id = new_session_id()
    st.session_state.interview_flow_version = 4


def clear_resume_state(*, clear_upload: bool = False) -> None:
    """清空简历、RAG 和岗位匹配状态。

    Args:
        clear_upload: `clear_upload` 关键字参数，类型为 bool。

    """
    st.session_state.resume_text = ""
    st.session_state.resume_retriever = None
    st.session_state.resume_signature = None
    st.session_state.resume_name = None
    st.session_state.resume_chars = 0
    st.session_state.resume_error = None
    st.session_state.resume_rag_mode = None
    st.session_state.job_match = None
    if clear_upload:
        st.session_state.resume_upload_version = int(
            st.session_state.get("resume_upload_version", 0)
        ) + 1


def reset_interview_state() -> None:
    """重置一次面试的全部状态并清理草稿。"""
    clear_current_draft()
    st.session_state.pending_draft = None
    st.session_state.current_stage_idx = 0
    st.session_state.stage_main_index = 0
    st.session_state.stage_followup_count = 0
    st.session_state.messages = []
    st.session_state.feedback = None
    st.session_state.structured_report = None
    st.session_state.current_question = ""
    st.session_state.question_audio = None
    st.session_state.question_audio_error = None
    st.session_state.session_id = new_session_id()
    st.session_state.start_time = None
    st.session_state.stage_started_at = None
    st.session_state.timer_alert = False
    st.session_state.interview_started_at = None
    st.session_state.report_duration_seconds = None
    st.session_state.report_duration_is_demo = False
    st.session_state.last_record_path = None
    st.session_state.last_record_markdown = None
    st.session_state.agent_run = None
    st.session_state.model_budget = default_usage_budget()
    st.session_state.consent_granted = False
    st.session_state.consent_at = None
    st.session_state.last_tags = []
    clear_resume_state(clear_upload=True)
    st.session_state.job_description = ""
    st.session_state.job_match = None
    st.session_state.job_description_input = ""
    st.session_state.setup_step = 1
    st.session_state.current_view = "setup"
    st.session_state.nav_version = st.session_state.get("nav_version", 0) + 1
# ===================== 语音辅助 =====================
def set_question_audio(question: str) -> None:
    """把面试题合成为语音并写入会话状态。

    Args:
        question: `question` 输入参数，类型为 str。

    """
    try:
        st.session_state.question_audio = text2audio(question)
        st.session_state.question_audio_error = None
    except Exception as exc:
        st.session_state.question_audio = None
        st.session_state.question_audio_error = str(exc)
# ===================== 面试业务 =====================
def extract_tags(review_text: str, valid_tags: list[str]) -> list[str]:
    """调用模型从复盘中提取合法薄弱标签。

    Args:
        review_text: `review_text` 输入参数，类型为 str。
        valid_tags: `valid_tags` 输入参数，类型为 list[str]。

    Returns:
        函数处理结果，类型为 list[str]。

    """
    try:
        result = MODEL_GATEWAY.complete(
            "tagging",
            "",
            build_tag_prompt(review_text, valid_tags),
            budget=st.session_state.get("model_budget"),
            tenant_id=st.session_state.get("tenant_id", "local"),
        )
        record_model_call(result, "model.tagging")
        raw = result.content.strip()
        return parse_tags(raw, valid_tags)
    except Exception:
        return []


def update_global_stats(mode: str, tags: list[str]) -> None:
    """累加当前租户的薄弱标签统计。

    Args:
        mode: `mode` 输入参数，类型为 str。
        tags: `tags` 输入参数，类型为 list[str]。

    """
    mode_stats = st.session_state.global_weak_stats.setdefault(mode, {})
    for tag in tags:
        mode_stats[tag] = mode_stats.get(tag, 0) + 1
    save_global_weak_stats(st.session_state.global_weak_stats)


def get_stage_question(
    mode: str,
    stage_idx: int,
    resume_ctx: str,
    weak_stats: dict,
    main_index: int,
    followup_index: int = 0,
    is_followup: bool = False,
    previous_question: str = "",
    last_answer: str = "",
    job_ctx: str = "",
) -> str:
    """按阶段、主问题和追问上下文生成面试题。

    Args:
        mode: `mode` 输入参数，类型为 str。
        stage_idx: `stage_idx` 输入参数，类型为 int。
        resume_ctx: `resume_ctx` 输入参数，类型为 str。
        weak_stats: `weak_stats` 输入参数，类型为 dict。
        main_index: `main_index` 输入参数，类型为 int。
        followup_index: `followup_index` 输入参数，类型为 int。
        is_followup: `is_followup` 输入参数，类型为 bool。
        previous_question: `previous_question` 输入参数，类型为 str。
        last_answer: `last_answer` 输入参数，类型为 str。
        job_ctx: `job_ctx` 输入参数，类型为 str。

    Returns:
        函数处理结果，类型为 str。

    """
    stage = MODE_CONFIG[mode]["stage_list"][stage_idx]
    prompt = build_stage_question_prompt(
        mode=mode,
        style=st.session_state.style,
        stage=stage,
        resume_ctx=resume_ctx,
        weak_stats=weak_stats,
        main_index=main_index,
        followup_index=followup_index,
        is_followup=is_followup,
        previous_question=previous_question,
        last_answer=last_answer,
        job_ctx=job_ctx,
    )
    result = MODEL_GATEWAY.complete(
        "question",
        prompt.system_prompt,
        "请给出当前这一题",
        budget=st.session_state.get("model_budget"),
        tenant_id=st.session_state.get("tenant_id", "local"),
    )
    record_model_call(result, "model.question")
    question = result.content
    if previous_question and last_answer and questions_too_similar(question, previous_question):
        repair_result = MODEL_GATEWAY.complete(
            "question",
            build_repair_prompt(prompt.system_prompt),
            "请重新给出一个不同的问题",
            budget=st.session_state.get("model_budget"),
            tenant_id=st.session_state.get("tenant_id", "local"),
        )
        record_model_call(repair_result, "model.question.repair")
        question = repair_result.content
    if previous_question and last_answer and questions_too_similar(question, previous_question):
        question = build_similarity_fallback(prompt.current_topic, last_answer)
    return question


def get_weak_question(mode: str) -> str:
    """针对最高频薄弱标签生成专项练习题。

    Args:
        mode: `mode` 输入参数，类型为 str。

    Returns:
        函数处理结果，类型为 str。

    """
    stats = st.session_state.global_weak_stats[mode]
    if not stats:
        return MODE_CONFIG[mode]["stage_list"][0]["pool"][0]
    top_tag = max(stats.items(), key=lambda item: item[1])[0]
    prompt = f"【{mode}】薄弱点：{top_tag}，生成一道面试题，只输出题目。"
    result = MODEL_GATEWAY.complete(
        "question",
        "你是面试出题专家",
        prompt,
        budget=st.session_state.get("model_budget"),
        tenant_id=st.session_state.get("tenant_id", "local"),
    )
    record_model_call(result, "model.question.weak")
    return result.content


def generate_review(mode_cfg: dict) -> bool:
    """生成定性复盘和结构化报告，保存会话并清理草稿。

    Args:
        mode_cfg: `mode_cfg` 输入参数，类型为 dict。

    Returns:
        函数处理结果，类型为 bool。

    Raises:
        RuntimeError: 当输入、状态或外部依赖不满足要求时抛出 RuntimeError。

    """
    if not st.session_state.messages:
        st.warning("还没有对话记录，至少回答一道题后再生成复盘")
        return False

    tag_list = mode_cfg["tags"]
    reviewer_prompt = build_review_prompt(
        mode=st.session_state.mode,
        style=st.session_state.style,
        valid_tags=tag_list,
        messages=st.session_state.messages,
    )
    try:
        result = MODEL_GATEWAY.complete(
            "review",
            reviewer_prompt,
            "",
            budget=st.session_state.get("model_budget"),
            tenant_id=st.session_state.get("tenant_id", "local"),
        )
        record_model_call(result, "model.review")
        feedback = strip_numeric_scores(result.content)
        if not feedback:
            raise RuntimeError("面试官总评为空，请重试复盘生成")
    except Exception as exc:
        record_run_error(exc, "model.review.failed")
        st.error(str(exc))
        return False

    st.session_state.feedback = feedback
    agent_run = st.session_state.get("agent_run")
    tags = extract_tags(feedback, tag_list)
    st.session_state.last_tags = tags
    scenario = SCENARIO_REGISTRY.scenario_for_round(st.session_state.mode)
    structured_report = build_interview_report(
        st.session_state.messages,
        scenario.rubric,
        tags,
        st.session_state.get("job_match"),
    )
    st.session_state.structured_report = structured_report
    try:
        update_global_stats(st.session_state.mode, tags)
    except Exception as exc:
        st.warning(f"薄弱统计更新失败：{exc}")
    if agent_run is not None:
        agent_run.record_event(
            "evaluation.completed",
            "interview.evaluation",
            {
                "feedback_chars": len(feedback),
                "tag_count": len(tags),
                "tags": tags,
                "overall_score": structured_report.overall_score,
                "dimensions": [
                    {"name": item.name, "score": item.score}
                    for item in structured_report.dimensions
                ],
            },
        )
    try:
        save_session(st.session_state.mode, st.session_state.messages, feedback, tags)
    except Exception as exc:
        st.warning(f"复盘已生成，但保存失败：{exc}")
    else:
        clear_current_draft()
    return True


def process_answer(ans_text: str, mode_cfg: dict) -> bool:
    """处理候选人回答并推进面试流程。

    Args:
        ans_text: `ans_text` 输入参数，类型为 str。
        mode_cfg: `mode_cfg` 输入参数，类型为 dict。

    Returns:
        函数处理结果，类型为 bool。

    """
    current_question = str(st.session_state.get("current_question") or "")
    current_stage_idx = int(st.session_state.get("current_stage_idx", 0))
    agent_run = st.session_state.get("agent_run")

    if is_explicit_end_request(ans_text):
        st.session_state.messages.extend(
            [
                {"role": "interviewer", "content": current_question},
                {"role": "candidate", "content": ans_text},
            ]
        )
        if agent_run is not None:
            agent_run.record_event(
                "answer.received",
                "interview.answer",
                {"answer_length": len(ans_text)},
            )
        if generate_review(mode_cfg):
            return True
        del st.session_state.messages[-2:]
        save_current_draft()
        return False

    ctx = query_resume(
        st.session_state.resume_retriever,
        current_question + "\n" + ans_text,
    )
    job_ctx = current_job_context()
    commit_stage_idx = current_stage_idx
    commit_main_index = int(st.session_state.get("stage_main_index", 0))
    commit_followup_count = int(st.session_state.get("stage_followup_count", 0))

    if st.session_state.interview_type == "闯关全真面试":
        current_stage = mode_cfg["stage_list"][current_stage_idx]
        question_plan = current_stage.get("question_plan") or current_stage["pool"]
        decision = decide_next_step(
            main_count=len(question_plan),
            main_index=commit_main_index,
            followup_count=commit_followup_count,
            max_followups=int(current_stage.get("max_followups", 0)),
            answer=ans_text,
            is_last_stage=current_stage_idx == len(mode_cfg["stage_list"]) - 1,
        )

        if decision.action is FlowAction.FOLLOW_UP:
            try:
                question = get_stage_question(
                    st.session_state.mode,
                    current_stage_idx,
                    ctx,
                    st.session_state.global_weak_stats[st.session_state.mode],
                    decision.main_index,
                    decision.followup_count,
                    True,
                    previous_question=current_question,
                    last_answer=ans_text,
                    job_ctx=job_ctx,
                )
            except Exception as exc:
                record_run_error(exc, "model.question.failed")
                st.error(str(exc))
                return False
            commit_main_index = decision.main_index
            commit_followup_count = decision.followup_count
        elif decision.action is FlowAction.NEXT_MAIN:
            try:
                question = get_stage_question(
                    st.session_state.mode,
                    current_stage_idx,
                    ctx,
                    st.session_state.global_weak_stats[st.session_state.mode],
                    decision.main_index,
                    0,
                    False,
                    previous_question=current_question,
                    last_answer=ans_text,
                    job_ctx=job_ctx,
                )
            except Exception as exc:
                record_run_error(exc, "model.question.failed")
                st.error(str(exc))
                return False
            commit_main_index = decision.main_index
            commit_followup_count = 0
        elif decision.action is FlowAction.NEXT_STAGE:
            next_stage_idx = current_stage_idx + 1
            try:
                question = get_stage_question(
                    st.session_state.mode,
                    next_stage_idx,
                    ctx,
                    st.session_state.global_weak_stats[st.session_state.mode],
                    0,
                    0,
                    False,
                    previous_question=current_question,
                    last_answer=ans_text,
                    job_ctx=job_ctx,
                )
            except Exception as exc:
                record_run_error(exc, "model.question.failed")
                st.error(str(exc))
                return False
            commit_stage_idx = next_stage_idx
            commit_main_index = 0
            commit_followup_count = 0
        else:
            question = "本次面试所有阶段完成，你可以点击“结束面试并生成复盘”。"
            commit_stage_idx = len(mode_cfg["stage_list"])
            commit_main_index = 0
            commit_followup_count = 0
    else:
        try:
            question = get_weak_question(st.session_state.mode)
        except Exception as exc:
            record_run_error(exc, "model.question.failed")
            st.error(str(exc))
            return False

    st.session_state.messages.extend(
        [
            {"role": "interviewer", "content": current_question},
            {"role": "candidate", "content": ans_text},
        ]
    )
    if agent_run is not None:
        agent_run.record_event(
            "answer.received",
            "interview.answer",
            {"answer_length": len(ans_text)},
        )
    if commit_stage_idx != current_stage_idx:
        record_stage_transition(mode_cfg, current_stage_idx, commit_stage_idx)
        st.session_state.stage_started_at = time.time()
    st.session_state.current_stage_idx = commit_stage_idx
    st.session_state.stage_main_index = commit_main_index
    st.session_state.stage_followup_count = commit_followup_count
    st.session_state.current_question = question
    record_question_generated(
        question,
        mode_cfg,
        commit_stage_idx,
        commit_main_index,
        commit_followup_count,
    )
    set_question_audio(question)
    save_current_draft()
    return True


@st.fragment(run_every="1s", key="interview_timer_fragment")
def render_interview_timer() -> None:
    """渲染总时长和阶段剩余时间计时器。"""
    scenario = SCENARIO_REGISTRY.scenario_for_round(st.session_state.mode)
    total_seconds = max(1, int(scenario.duration_minutes) * 60)
    elapsed = time.time() - st.session_state.start_time
    remain = max(0, total_seconds - elapsed)
    minutes, seconds = int(remain // 60), int(remain % 60)

    stage_idx = int(st.session_state.get("current_stage_idx", 0))
    stage_text = ""
    stage_expired = False
    if stage_idx < len(scenario.stages):
        stage = scenario.stages[stage_idx]
        stage_started_at = st.session_state.get("stage_started_at") or st.session_state.start_time
        stage_budget = max(1, int(stage.time_budget_min) * 60)
        stage_remain = max(0, stage_budget - (time.time() - stage_started_at))
        stage_minutes, stage_seconds = int(stage_remain // 60), int(stage_remain % 60)
        stage_text = f" · {stage.name} {stage_minutes:02d}:{stage_seconds:02d}"
        stage_expired = stage_remain <= 0

    st.markdown(
        f'<div class="il-timer-row"><span class="il-timer-pill">'
        f"⏱ {minutes:02d}:{seconds:02d}{stage_text}</span></div>",
        unsafe_allow_html=True,
    )
    if stage_expired:
        st.caption("本阶段建议时间已到，建议完成当前问题后进入下一阶段。")
    if remain <= 0 and not st.session_state.timer_alert:
        st.warning("面试时长已到，建议结束面试生成复盘。")
        st.session_state.timer_alert = True


# ===================== 页面导航与 UI 装配 =====================
BASE_VIEW_ORDER = ["dashboard", "setup", "interview", "report", "growth"]
VIEW_LABELS = {
    "dashboard": "工作台",
    "setup": "开始面试",
    "interview": "面试室",
    "report": "复盘报告",
    "growth": "成长记录",
    "admin": "管理控制台",
}


def visible_views() -> list[str]:
    """返回当前可见的页面列表，按开关追加控制台。

    Returns:
        函数处理结果，类型为 list[str]。

    """
    views = list(BASE_VIEW_ORDER)
    if ADMIN_MODE:
        views.append("admin")
    return views


def set_view(view: str) -> None:
    """切换当前页面并递增导航版本。

    Args:
        view: `view` 输入参数，类型为 str。

    """
    if view == "admin" and not ADMIN_MODE:
        view = "dashboard"
    st.session_state.current_view = view
    st.session_state.nav_version = st.session_state.get("nav_version", 0) + 1


def go_to(view: str) -> None:
    """切换页面并立即重跑。

    Args:
        view: `view` 输入参数，类型为 str。

    """
    set_view(view)
    st.rerun()


def finish_interview_confirmed(mode_cfg: dict) -> None:
    """确认结束后生成复盘并跳转到报告页。

    Args:
        mode_cfg: `mode_cfg` 输入参数，类型为 dict。

    """
    if generate_review(mode_cfg):
        set_view("report")
        st.rerun()


@st.dialog("确认结束面试")
def confirm_finish_interview(mode_cfg: dict) -> None:
    """弹出结束面试确认对话框。

    Args:
        mode_cfg: `mode_cfg` 输入参数，类型为 dict。

    """
    st.write(
        "结束后将生成当前已完成回答的复盘和 Markdown 记录。"
        "未作答的后续问题不会自动补齐。"
    )
    cancel_col, confirm_col = st.columns(2)
    if cancel_col.button(
        "继续面试",
        key="cancel_finish_interview",
        width="stretch",
    ):
        st.rerun()
    confirm_col.button(
        "确认结束",
        type="primary",
        key="confirm_finish_interview",
        width="stretch",
        on_click=finish_interview_confirmed,
        args=(mode_cfg,),
    )


def render_sidebar() -> None:
    """渲染侧边栏导航和面试状态。"""
    with st.sidebar:
        st.markdown("### InterviewLoop")
        st.caption("AI 面试训练平台")
        if DEMO_MODE:
            st.caption("当前为演示模式")
        views = visible_views()
        current = st.session_state.get("current_view", "dashboard")
        if current not in views:
            current = "dashboard"
            st.session_state.current_view = current
        index = views.index(current)
        nav_version = int(st.session_state.get("nav_version", 0))
        selected = st.radio(
            "主导航",
            [VIEW_LABELS[item] for item in views],
            index=index,
            key=f"main_navigation_{nav_version}",
            label_visibility="collapsed",
        )
        selected_view = next(
            view for view in views if VIEW_LABELS[view] == selected
        )
        if selected_view != current:
            if selected_view == "setup":
                enter_setup_view()
            else:
                st.session_state.current_view = selected_view
                st.session_state.nav_version += 1
            st.rerun()

        st.caption(f"{st.session_state.mode}  {st.session_state.style}")
        if st.session_state.get("start_time") is not None:
            status = "已完成" if st.session_state.get("feedback") else "进行中"
            st.caption(f"面试状态：{status}")
        if st.button("新建面试", key="sidebar_new_interview", width="stretch"):
            reset_interview_state()
            st.rerun()


def render_dashboard() -> None:
    """渲染工作台并装配最近会话和草稿回调。"""
    sessions = list_session_files()
    latest = None
    if sessions:
        try:
            latest = json.loads(sessions[0].read_text(encoding="utf-8"))
        except Exception:
            latest = None
    weak_items = sum(
        int(value)
        for value in st.session_state.global_weak_stats.get(st.session_state.mode, {}).values()
    )
    pending_draft = st.session_state.get("pending_draft")
    if st.session_state.get("start_time") is not None:
        pending_draft = None

    def open_growth() -> None:
        """跳转到成长记录页。"""
        go_to("growth")

    render_dashboard_view(
        sessions=sessions,
        latest=latest,
        weak_items=weak_items,
        current_mode=st.session_state.mode,
        pending_draft=pending_draft,
        on_start=open_setup_view,
        on_growth=open_growth,
        on_report=open_latest_report,
        on_restore=restore_pending_draft,
        on_discard=discard_pending_draft,
    )


def start_interview_session(mode_cfg: dict) -> None:
    """开始一场面试并生成第一道题。

    Args:
        mode_cfg: `mode_cfg` 输入参数，类型为 dict。

    """
    if (
        st.session_state.interview_type == "闯关全真面试"
        and st.session_state.current_stage_idx
        >= len(mode_cfg["stage_list"])
    ):
        st.warning("所有阶段已完成，请开启新一轮面试。")
    else:
        st.session_state.model_budget = default_usage_budget()
        agent_run = AgentRun(
            tenant_id=current_tenant_id(),
            user_id=st.session_state.get("user_id", "local"),
            retention_policy=st.session_state.get("retention_policy", "standard"),
            consent_granted=st.session_state.get("consent_granted", False),
            consent_at=st.session_state.get("consent_at"),
            metadata={
                "mode": st.session_state.mode,
                "scenario_id": SCENARIO_REGISTRY.scenario_for_round(
                    st.session_state.mode
                ).id,
                "interview_type": st.session_state.interview_type,
                "style": st.session_state.style,
                "job_match_score": (
                    st.session_state.job_match.match_score
                    if isinstance(st.session_state.get("job_match"), JobMatchReport)
                    else None
                ),
                "missing_skills": (
                    list(st.session_state.job_match.missing_skills)
                    if isinstance(st.session_state.get("job_match"), JobMatchReport)
                    else []
                ),
            },
        )
        agent_run.start("interview.start")
        st.session_state.agent_run = agent_run
        try:
            with st.spinner("正在生成第一道题..."):
                ctx = query_resume(st.session_state.resume_retriever, "")
                if st.session_state.interview_type == "闯关全真面试":
                    question = get_stage_question(
                        st.session_state.mode,
                        st.session_state.current_stage_idx,
                        ctx,
                        st.session_state.global_weak_stats[st.session_state.mode],
                        st.session_state.stage_main_index,
                        st.session_state.stage_followup_count,
                        st.session_state.stage_followup_count > 0,
                        job_ctx=current_job_context(),
                    )
                else:
                    question = get_weak_question(st.session_state.mode)
        except Exception as exc:
            record_run_error(exc, "interview.start.failed")
            st.error(str(exc))
        else:
            started_now = time.time()
            st.session_state.start_time = started_now
            st.session_state.stage_started_at = started_now
            st.session_state.interview_started_at = time.strftime(
                "%Y-%m-%d_%H-%M-%S"
            )
            st.session_state.current_question = question
            record_question_generated(
                question,
                mode_cfg,
                st.session_state.current_stage_idx,
                st.session_state.stage_main_index,
                st.session_state.stage_followup_count,
            )
            set_question_audio(question)
            save_current_draft()
            set_view("interview")
            st.rerun()


def render_setup(mode_cfg: dict) -> None:
    """渲染面试设置页。

    Args:
        mode_cfg: `mode_cfg` 输入参数，类型为 dict。

    """
    render_setup_view(
        mode_cfg,
        reset_interview_state=reset_interview_state,
        clear_resume_state=clear_resume_state,
        start_interview=start_interview_session,
        continue_interview=lambda: go_to("interview"),
    )


def render_interview(mode_cfg: dict) -> None:
    """渲染面试室。

    Args:
        mode_cfg: `mode_cfg` 输入参数，类型为 dict。

    """
    render_interview_view(
        mode_cfg,
        render_timer=render_interview_timer,
        process_answer=process_answer,
        open_setup=open_setup_view,
        confirm_finish=confirm_finish_interview,
    )


def render_report() -> None:
    """渲染复盘报告页。"""
    feedback = st.session_state.get("feedback")
    duration_seconds = st.session_state.get("report_duration_seconds")
    if duration_seconds is None and st.session_state.get("start_time") is not None:
        duration_seconds = int(max(0, time.time() - st.session_state.start_time))

    def start_new_interview() -> None:
        """跳转到面试设置页。"""
        go_to("setup")

    def restart_interview() -> None:
        """重置并开始新一轮面试。"""
        reset_interview_state()
        st.rerun()

    def open_growth() -> None:
        """跳转到成长记录页。"""
        go_to("growth")

    render_report_view(
        feedback=feedback,
        duration_seconds=duration_seconds,
        tags=list(st.session_state.get("last_tags", [])),
        structured_report=st.session_state.get("structured_report"),
        job_match=st.session_state.get("job_match"),
        messages_count=len(st.session_state.get("messages", [])),
        demo_mode=bool(st.session_state.get("report_duration_is_demo", False)),
        last_record_path=st.session_state.get("last_record_path"),
        last_record_markdown=st.session_state.get("last_record_markdown"),
        mode=st.session_state.mode,
        interview_type=st.session_state.interview_type,
        style=st.session_state.style,
        on_start=start_new_interview,
        on_again=restart_interview,
        on_growth=open_growth,
    )


def render_growth(mode_cfg: dict) -> None:
    """渲染成长记录页。

    Args:
        mode_cfg: `mode_cfg` 输入参数，类型为 dict。

    """
    def open_session(saved: dict, session_file: Path) -> None:
        """加载历史会话并跳转到报告或设置页。

        Args:
            saved: `saved` 输入参数，类型为 dict。
            session_file: `session_file` 输入参数，类型为 Path。

        """
        load_saved_session_into_state(saved, session_file)
        set_view("report" if saved.get("feedback") else "setup")
        st.rerun()

    def delete_session(
        session_file: Path,
        markdown_path: Path,
        saved: dict,
    ) -> None:
        """删除会话 JSON、Markdown 记录和对应草稿。

        Args:
            session_file: `session_file` 输入参数，类型为 Path。
            markdown_path: `markdown_path` 输入参数，类型为 Path。
            saved: `saved` 输入参数，类型为 dict。

        """
        session_file.unlink(missing_ok=True)
        markdown_path.unlink(missing_ok=True)
        delete_interview_draft(
            tenant_save_dir(),
            str(saved.get("session_id", "")),
        )
        st.session_state.delete_confirm_id = None
        st.rerun()

    render_growth_view(
        mode_list=MODE_LIST,
        mode_config=MODE_CONFIG,
        current_mode=st.session_state.mode,
        weak_stats=st.session_state.global_weak_stats,
        session_files=list_session_files(),
        record_dir=tenant_record_dir(),
        save_weak_stats=save_global_weak_stats,
        open_session=open_session,
        delete_session=delete_session,
        budget=st.session_state.get("model_budget"),
        tenant_snapshot=TENANT_QUOTA_STORE.snapshot(current_tenant_id()),
        agent_run=st.session_state.get("agent_run"),
    )


@st.cache_data(ttl=300, show_spinner=False)
def cached_rag_metrics() -> dict:
    """缓存并返回默认 RAG 黄金集评估指标。

    Returns:
        函数处理结果，类型为 dict。

    """
    return evaluate_default_rag()


def render_admin() -> None:
    """渲染只读平台控制台。"""
    render_admin_view(
        registry=SCENARIO_REGISTRY,
        tool_registry=TOOL_REGISTRY,
        model_gateway=MODEL_GATEWAY,
        tenant_quota_store=TENANT_QUOTA_STORE,
        base_dir=BASE_DIR,
        db_path=agent_run_repository_path(),
        rag_metrics=cached_rag_metrics(),
        tenant_id=current_tenant_id(),
    )


mode_cfg = MODE_CONFIG[st.session_state.mode]
render_sidebar()
view = st.session_state.get("current_view", "dashboard")
if view == "dashboard":
    render_dashboard()
elif view == "setup":
    render_setup(mode_cfg)
elif view == "interview":
    render_interview(mode_cfg)
elif view == "report":
    render_report()
elif view == "admin":
    render_admin()
else:
    render_growth(mode_cfg)

st.caption("InterviewLoop  结构化面试  证据化复盘  持续训练")
