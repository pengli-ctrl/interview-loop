import hashlib
import json
import time
from pathlib import Path

import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="InterviewLoop",
    page_icon=":material/psychology_alt:",
    layout="wide",
)

from interview_loop.config import (
    DEMO_MODE,
    GLOBAL_STATS_PATH,
    MODE_CONFIG,
    MODE_LIST,
    RECORD_DIR,
    SAVE_DIR,
    SCENARIO_REGISTRY,
    STYLE_LIST,
)
from interview_loop.core.flow import FlowAction, decide_next_step
from interview_loop.core.job_match import (
    JobDescriptionError,
    JobMatchReport,
    assess_job_match,
    build_job_context,
    load_default_skill_catalog,
)
from interview_loop.core.question_engine import (
    build_repair_prompt,
    build_similarity_fallback,
    build_stage_question_prompt,
    questions_too_similar,
)
from interview_loop.core.review import build_review_prompt, build_tag_prompt, parse_tags
from interview_loop.export.markdown import safe_filename_part
from interview_loop.platform.agent_run import AgentRun, RunStatus
from interview_loop.platform.builtin_tools import build_default_tool_registry
from interview_loop.platform.model_gateway import (
    ModelGateway,
    default_tenant_quota_store,
    default_usage_budget,
)
from interview_loop.rag.resume import extract_resume_text
from interview_loop.rag.retriever import build_rag, query_resume
from interview_loop.services.asr import audio2text
from interview_loop.services.tts import text2audio
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

SKILL_CATALOG = load_default_skill_catalog()
TENANT_QUOTA_STORE = default_tenant_quota_store()
MODEL_GATEWAY = ModelGateway(tenant_quota_store=TENANT_QUOTA_STORE)
TOOL_REGISTRY = build_default_tool_registry()


def record_model_call(result, node: str) -> None:
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
    agent_run = st.session_state.get("agent_run")
    if agent_run is None:
        return
    agent_run.record_event("run.error", node, {"error": str(error)[:500]})


def current_job_context() -> str:
    report = st.session_state.get("job_match")
    return build_job_context(report) if isinstance(report, JobMatchReport) else ""


def record_question_generated(
    question: str,
    mode_cfg: dict,
    stage_idx: int,
    main_index: int,
    followup_index: int,
) -> None:
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


# ===================== 持久化与初始化 =====================
def current_tenant_id() -> str:
    return st.session_state.get("tenant_id", "local")


def tenant_save_dir() -> Path:
    path = tenant_scoped_dir(SAVE_DIR, current_tenant_id())
    path.mkdir(parents=True, exist_ok=True)
    return path


def tenant_record_dir() -> Path:
    path = tenant_scoped_dir(RECORD_DIR, current_tenant_id())
    path.mkdir(parents=True, exist_ok=True)
    return path


def list_session_files() -> list[Path]:
    return _list_session_files(tenant_save_dir())


def save_global_weak_stats(stats: dict) -> None:
    save_stats(GLOBAL_STATS_PATH, stats)


def save_session(mode: str, messages: list, feedback: str, tags: list[str]) -> Path:
    started_at = st.session_state.get("interview_started_at") or time.strftime(
        "%Y-%m-%d_%H-%M-%S"
    )
    duration_seconds = None
    if st.session_state.get("start_time") is not None:
        duration_seconds = int(max(0, time.time() - st.session_state.start_time))

    agent_run = st.session_state.get("agent_run")
    job_match = st.session_state.get("job_match")
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
        data["agent_run"] = agent_run.to_dict()
    budget = st.session_state.get("model_budget")
    if budget is not None:
        data["model_usage"] = budget.to_dict()
    json_path = save_session_json(tenant_save_dir(), data)
    st.session_state.last_record_path = str(markdown_path)
    st.session_state.last_record_markdown = markdown
    st.session_state.session_list = list_session_files()
    return json_path


# 初始化 session state
_initial_weak_stats, _weak_stats_error = load_stats(GLOBAL_STATS_PATH, MODE_LIST)
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
    "question_audio": None,
    "question_audio_error": None,
    "last_audio_digest": None,
    "global_weak_stats": _initial_weak_stats,
    "start_time": None,
    "timer_alert": False,
    "interview_started_at": None,
    "last_record_path": None,
    "last_record_markdown": None,
    "agent_run": None,
    "model_budget": default_usage_budget(),
    "session_list": list_session_files(),
}
for key, value in defaults.items():
    st.session_state.setdefault(key, value)
st.session_state.setdefault("style", MODE_CONFIG[st.session_state.mode]["default_style"])

# 60 分钟面试：每阶段按主问题计划执行，并根据回答动态追问。
if st.session_state.get("interview_flow_version") != 4:
    st.session_state.current_stage_idx = 0
    st.session_state.stage_main_index = 0
    st.session_state.stage_followup_count = 0
    st.session_state.messages = []
    st.session_state.feedback = None
    st.session_state.current_question = ""
    st.session_state.start_time = None
    st.session_state.interview_started_at = None
    st.session_state.last_record_path = None
    st.session_state.last_record_markdown = None
    st.session_state.agent_run = None
    st.session_state.model_budget = default_usage_budget()
    st.session_state.consent_granted = False
    st.session_state.consent_at = None
    st.session_state.session_id = new_session_id()
    st.session_state.interview_flow_version = 4


def reset_interview_state() -> None:
    st.session_state.current_stage_idx = 0
    st.session_state.stage_main_index = 0
    st.session_state.stage_followup_count = 0
    st.session_state.messages = []
    st.session_state.feedback = None
    st.session_state.current_question = ""
    st.session_state.question_audio = None
    st.session_state.question_audio_error = None
    st.session_state.session_id = new_session_id()
    st.session_state.start_time = None
    st.session_state.timer_alert = False
    st.session_state.interview_started_at = None
    st.session_state.last_record_path = None
    st.session_state.last_record_markdown = None
    st.session_state.agent_run = None
    st.session_state.model_budget = default_usage_budget()
    st.session_state.consent_granted = False
    st.session_state.consent_at = None
    st.session_state.last_tags = []
    st.session_state.resume_text = ""
    st.session_state.job_description = ""
    st.session_state.job_match = None
    st.session_state.job_description_input = ""
    st.session_state.setup_step = 1
    st.session_state.current_view = "setup"
    st.session_state.nav_version = st.session_state.get("nav_version", 0) + 1
# ===================== 简历解析与 RAG =====================
def set_question_audio(question: str) -> None:
    try:
        st.session_state.question_audio = text2audio(question)
        st.session_state.question_audio_error = None
    except Exception as exc:
        st.session_state.question_audio = None
        st.session_state.question_audio_error = str(exc)
# ===================== 面试业务 =====================
def extract_tags(review_text: str, valid_tags: list[str]) -> list[str]:
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
        feedback = result.content
    except Exception as exc:
        record_run_error(exc, "model.review.failed")
        st.error(str(exc))
        return False

    st.session_state.feedback = feedback
    agent_run = st.session_state.get("agent_run")
    tags = extract_tags(feedback, tag_list)
    st.session_state.last_tags = tags
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
            },
        )
    try:
        save_session(st.session_state.mode, st.session_state.messages, feedback, tags)
    except Exception as exc:
        st.warning(f"复盘已生成，但保存失败：{exc}")
    return True


def process_answer(ans_text: str, mode_cfg: dict) -> bool:
    st.session_state.messages.append(
        {"role": "interviewer", "content": st.session_state.current_question}
    )
    st.session_state.messages.append({"role": "candidate", "content": ans_text})
    agent_run = st.session_state.get("agent_run")
    if agent_run is not None:
        agent_run.record_event(
            "answer.received",
            "interview.answer",
            {"answer_length": len(ans_text)},
        )

    if "结束面试" in ans_text:
        return generate_review(mode_cfg)

    ctx = query_resume(
        st.session_state.resume_retriever,
        f"{st.session_state.current_question}\n{ans_text}",
    )
    job_ctx = current_job_context()
    if st.session_state.interview_type == "闯关全真面试":
        current_stage_idx = st.session_state.current_stage_idx
        current_stage = mode_cfg["stage_list"][current_stage_idx]
        question_plan = current_stage.get("question_plan") or current_stage["pool"]
        decision = decide_next_step(
            main_count=len(question_plan),
            main_index=st.session_state.stage_main_index,
            followup_count=st.session_state.stage_followup_count,
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
                    previous_question=st.session_state.current_question,
                    last_answer=ans_text,
                    job_ctx=job_ctx,
                )
            except Exception as exc:
                record_run_error(exc, "model.question.failed")
                st.error(str(exc))
                return False
            st.session_state.stage_followup_count = decision.followup_count
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
                    previous_question=st.session_state.current_question,
                    last_answer=ans_text,
                    job_ctx=job_ctx,
                )
            except Exception as exc:
                record_run_error(exc, "model.question.failed")
                st.error(str(exc))
                return False
            st.session_state.stage_main_index = decision.main_index
            st.session_state.stage_followup_count = 0
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
                    previous_question=st.session_state.current_question,
                    last_answer=ans_text,
                    job_ctx=job_ctx,
                )
            except Exception as exc:
                record_run_error(exc, "model.question.failed")
                st.error(str(exc))
                return False
            st.session_state.current_stage_idx = next_stage_idx
            st.session_state.stage_main_index = 0
            st.session_state.stage_followup_count = 0
            record_stage_transition(mode_cfg, current_stage_idx, next_stage_idx)
        else:
            question = "本次面试所有阶段完成，你可以说【结束面试】或点击 Finish 生成复盘。"
            st.session_state.current_stage_idx = len(mode_cfg["stage_list"])
            st.session_state.stage_main_index = 0
            st.session_state.stage_followup_count = 0
            record_stage_transition(
                mode_cfg,
                current_stage_idx,
                len(mode_cfg["stage_list"]),
            )
    else:
        try:
            question = get_weak_question(st.session_state.mode)
        except Exception as exc:
            st.error(str(exc))
            return False

    st.session_state.current_question = question
    record_question_generated(
        question,
        mode_cfg,
        st.session_state.current_stage_idx,
        st.session_state.stage_main_index,
        st.session_state.stage_followup_count,
    )
    set_question_audio(question)
    return True


@st.fragment(run_every="1s", key="interview_timer_fragment")
def render_interview_timer() -> None:
    elapsed = time.time() - st.session_state.start_time
    remain = max(0, 60 * 60 - elapsed)
    minutes, seconds = int(remain // 60), int(remain % 60)
    st.metric("⏱️ 剩余面试时间", f"{minutes}分{seconds}秒")
    if remain <= 0 and not st.session_state.timer_alert:
        st.warning("⚠️ 60 分钟面试时长到，建议结束面试生成复盘")
        st.session_state.timer_alert = True


# ===================== UI =====================
VIEW_ORDER = ["dashboard", "setup", "interview", "report", "growth"]
VIEW_LABELS = {
    "dashboard": "工作台",
    "setup": "开始面试",
    "interview": "面试室",
    "report": "复盘报告",
    "growth": "成长记录",
}
LABEL_TO_VIEW = {label: view for view, label in VIEW_LABELS.items()}


def set_view(view: str) -> None:
    st.session_state.current_view = view
    st.session_state.nav_version = st.session_state.get("nav_version", 0) + 1


def go_to(view: str) -> None:
    set_view(view)
    st.rerun()


def render_sidebar() -> None:
    with st.sidebar:
        st.markdown("### InterviewLoop")
        st.caption("AI 面试训练平台")
        if DEMO_MODE:
            st.caption("当前为演示模式")
        current = st.session_state.get("current_view", "dashboard")
        index = VIEW_ORDER.index(current) if current in VIEW_ORDER else 0
        nav_version = int(st.session_state.get("nav_version", 0))
        selected = st.radio(
            "主导航",
            [VIEW_LABELS[item] for item in VIEW_ORDER],
            index=index,
            key=f"main_navigation_{nav_version}",
            label_visibility="collapsed",
        )
        selected_view = LABEL_TO_VIEW[selected]
        if selected_view != current:
            st.session_state.current_view = selected_view
            st.rerun()

        st.caption(f"{st.session_state.mode}  {st.session_state.style}")
        if st.session_state.get("start_time") is not None:
            status = "已完成" if st.session_state.get("feedback") else "进行中"
            st.caption(f"面试状态：{status}")
        if st.button("新建面试", key="sidebar_new_interview", width="stretch"):
            reset_interview_state()
            st.rerun()


def render_dashboard() -> None:
    st.title("InterviewLoop")
    st.caption("把一次面试练习，变成持续可见的能力成长。")

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

    with st.container(border=True):
        st.markdown("## 今天练什么？")
        st.write(
            "选择目标岗位和面试形式，完成一次完整模拟。结束后自动生成复盘、"
            "薄弱项和下一步训练建议。"
        )
        action_left, action_right = st.columns([1, 1])
        if action_left.button(
            "开始一次面试",
            type="primary",
            key="dashboard_start",
            width="stretch",
        ):
            go_to("setup")
        if action_right.button(
            "查看成长记录",
            key="dashboard_growth",
            width="stretch",
        ):
            go_to("growth")

    metric_cols = st.columns(3)
    metric_cols[0].metric("历史训练", len(sessions))
    metric_cols[1].metric("当前轮次", st.session_state.mode)
    metric_cols[2].metric("弱项记录", weak_items)

    st.subheader("训练入口")
    card_cols = st.columns(3)
    with card_cols[0].container(border=True, height="stretch"):
        st.markdown("#### 定向模拟")
        st.caption("按岗位轮次和风格完成一次结构化面试。")
        if st.button("进入设置", key="dashboard_card_setup", width="stretch"):
            go_to("setup")
    with card_cols[1].container(border=True, height="stretch"):
        st.markdown("#### 最近复盘")
        if latest and latest.get("feedback"):
            st.caption(str(latest.get("time", "最近一次面试")))
            if st.button("打开报告", key="dashboard_card_report", width="stretch"):
                go_to("report")
        else:
            st.caption("完成一次面试后，这里会显示最近复盘。")
    with card_cols[2].container(border=True, height="stretch"):
        st.markdown("#### 能力趋势")
        st.caption("查看历史记录、重复弱项和训练变化。")
        if st.button("查看成长", key="dashboard_card_growth", width="stretch"):
            go_to("growth")


def render_setup(mode_cfg: dict) -> None:
    st.header("设置一次面试")
    st.caption("先确定目标，再补充简历和授权信息。")

    if st.session_state.get("start_time") is not None and not st.session_state.get("feedback"):
        with st.container(border=True):
            st.markdown("### 当前面试尚未结束")
            st.write("继续当前面试，或新建一轮训练。")
            col_left, col_right = st.columns(2)
            if col_left.button("继续面试", type="primary", key="setup_continue_interview"):
                go_to("interview")
            if col_right.button("重置并重新设置", key="setup_reset_interview"):
                reset_interview_state()
                st.rerun()
        return

    step = int(st.session_state.get("setup_step", 1))
    st.progress(step / 3, text=f"设置进度：{step}/3")
    with st.container(border=True):
        if step == 1:
            st.subheader("1. 选择目标")
            new_mode = st.selectbox(
                "面试轮次",
                MODE_LIST,
                index=MODE_LIST.index(st.session_state.mode),
            )
            new_interview_type = st.segmented_control(
                "面试模式",
                ["闯关全真面试", "薄弱专项练习"],
                default=st.session_state.interview_type,
            )
            new_style = st.segmented_control(
                "面试官风格",
                STYLE_LIST,
                default=st.session_state.style,
            )
            if new_mode != st.session_state.mode:
                st.session_state.mode = new_mode
                st.session_state.style = MODE_CONFIG[new_mode]["default_style"]
                reset_interview_state()
                st.rerun()
            if new_interview_type != st.session_state.interview_type:
                st.session_state.interview_type = new_interview_type
                reset_interview_state()
                st.rerun()
            if new_style != st.session_state.style:
                st.session_state.style = new_style
            st.caption(MODE_CONFIG[st.session_state.mode]["desc"])
            if st.button("下一步：补充简历", type="primary", key="setup_next"):
                st.session_state.setup_step = 2
                st.rerun()
        elif step == 2:
            st.subheader("2. 补充上下文")
            jd_value = st.text_area(
                "目标岗位 JD（可选）",
                height=180,
                placeholder="粘贴目标岗位的职责、技能要求和任职资格。",
                key="job_description_input",
            )
            cleaned_jd = jd_value.strip()
            if cleaned_jd != st.session_state.get("job_description", ""):
                st.session_state.job_description = cleaned_jd
                st.session_state.job_match = None
            upload = st.file_uploader(
                "上传简历（可选）",
                type=["txt", "md", "pdf"],
                key="resume_upload",
            )
            if upload is not None:
                file_bytes = upload.getvalue()
                signature = hashlib.sha256(file_bytes).hexdigest()
                if signature != st.session_state.resume_signature:
                    st.session_state.resume_signature = signature
                    st.session_state.resume_retriever = None
                    st.session_state.resume_error = None
                    st.session_state.resume_rag_mode = None
                    st.session_state.resume_name = upload.name
                    st.session_state.resume_chars = 0
                    try:
                        with st.spinner("正在解析简历并构建 RAG 索引，只需执行一次..."):
                            resume_text = extract_resume_text(upload)
                            if not resume_text.strip():
                                raise ValueError("简历没有可提取的文本；扫描版 PDF 请先做 OCR")
                            retriever, rag_mode = build_rag(resume_text)
                            st.session_state.resume_retriever = retriever
                            st.session_state.resume_rag_mode = rag_mode
                            st.session_state.resume_chars = len(resume_text)
                            st.session_state.resume_text = resume_text
                            st.session_state.job_match = None
                    except Exception as exc:
                        st.session_state.resume_error = str(exc)
            if st.session_state.resume_error:
                st.error(f"简历加载失败：{st.session_state.resume_error}")
            elif st.session_state.resume_retriever is not None:
                st.caption(
                    f"已加载：{st.session_state.resume_name}  "
                    f"{st.session_state.resume_chars} 字符  "
                    f"检索模式：{st.session_state.resume_rag_mode}"
                )
            else:
                st.caption("不上传简历也可以开始；上传后可获得更贴近经历的问题。")

            saved_match = st.session_state.get("job_match")
            if isinstance(saved_match, JobMatchReport):
                st.markdown("#### 岗位匹配摘要")
                preview_cols = st.columns(3)
                preview_cols[0].metric("匹配度", f"{saved_match.match_score}/100")
                preview_cols[1].metric("已匹配", len(saved_match.matched_skills))
                preview_cols[2].metric("待补强", len(saved_match.missing_skills))
                if saved_match.missing_skills:
                    st.caption("缺失技能：" + "、".join(saved_match.missing_skills[:8]))

            col_left, col_right = st.columns(2)
            if col_left.button("上一步", key="setup_back"):
                st.session_state.setup_step = 1
                st.rerun()
            if col_right.button("下一步：确认并开始", type="primary", key="setup_next"):
                jd_text = st.session_state.get("job_description", "").strip()
                if jd_text:
                    try:
                        report = assess_job_match(
                            jd_text,
                            st.session_state.get("resume_text", ""),
                            SKILL_CATALOG,
                        )
                    except JobDescriptionError as exc:
                        st.error(str(exc))
                    else:
                        st.session_state.job_match = report
                        st.session_state.setup_step = 3
                        st.rerun()
                else:
                    st.session_state.job_match = None
                    st.session_state.setup_step = 3
                    st.rerun()
        else:
            st.subheader("3. 确认并开始")
            summary_cols = st.columns(3)
            summary_cols[0].metric("轮次", st.session_state.mode)
            summary_cols[1].metric("模式", st.session_state.interview_type)
            summary_cols[2].metric("风格", st.session_state.style)
            current_match = st.session_state.get("job_match")
            if isinstance(current_match, JobMatchReport):
                st.markdown("#### 岗位匹配")
                match_cols = st.columns(3)
                match_cols[0].metric("匹配度", f"{current_match.match_score}/100")
                match_cols[1].metric("已匹配技能", len(current_match.matched_skills))
                match_cols[2].metric("缺失技能", len(current_match.missing_skills))
                if current_match.missing_skills:
                    st.caption("面试将重点验证：" + "、".join(current_match.missing_skills[:5]))
            if st.session_state.get("resume_name"):
                st.caption(f"简历上下文：{st.session_state.resume_name}")
            else:
                st.caption("简历上下文：未上传")

            consent = st.checkbox(
                "我同意保存本次简历、文字或语音回答与复盘记录，并知悉数据保留策略。",
                value=st.session_state.consent_granted,
                key="consent_checkbox",
            )
            if consent and not st.session_state.consent_granted:
                st.session_state.consent_granted = True
                st.session_state.consent_at = time.strftime("%Y-%m-%d %H:%M:%S")
            elif not consent:
                st.session_state.consent_granted = False
                st.session_state.consent_at = None
            st.session_state.retention_policy = st.selectbox(
                "数据保留策略",
                ["ephemeral", "standard", "extended"],
                index=["ephemeral", "standard", "extended"].index(
                    st.session_state.retention_policy
                ),
                help="ephemeral=1天，standard=30天，extended=365天",
            )
            col_left, col_right = st.columns(2)
            if col_left.button("上一步", key="setup_back"):
                st.session_state.setup_step = 2
                st.rerun()
            if col_right.button(
                "开始面试计时",
                key="start_interview",
                type="primary",
                disabled=not st.session_state.consent_granted,
                width="stretch",
            ):
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
                        st.session_state.start_time = time.time()
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
                        set_view("interview")
                        st.rerun()


def render_interview(mode_cfg: dict) -> None:
    st.header("面试室")
    if st.session_state.get("start_time") is None or not st.session_state.get("current_question"):
        with st.container(border=True):
            st.markdown("### 还没有进行中的面试")
            st.write("先完成面试设置，再进入专注面试模式。")
            if st.button("去设置面试", type="primary", key="interview_empty_setup"):
                go_to("setup")
        return

    stages = mode_cfg["stage_list"]
    current_stage_idx = st.session_state.current_stage_idx
    all_done = (
        st.session_state.interview_type == "闯关全真面试"
        and current_stage_idx >= len(stages)
    )
    if not all_done:
        current_stage = stages[current_stage_idx]
        question_plan = current_stage.get("question_plan") or current_stage["pool"]
        main_total = max(1, len(question_plan))
        main_current = min(st.session_state.stage_main_index + 1, main_total)
        max_followups = max(0, int(current_stage.get("max_followups", 0)))
        followup_text = (
            f"  追问 {st.session_state.stage_followup_count}/{max_followups}"
            if max_followups
            else ""
        )
        st.progress(
            (current_stage_idx + 1) / len(stages),
            text=(
                f"阶段 {current_stage_idx + 1}/{len(stages)}  {current_stage['name']}  "
                f"主问题 {main_current}/{main_total}{followup_text}"
            ),
        )

    render_interview_timer()

    with st.container(border=True):
        st.caption("面试官")
        st.markdown(f"## {st.session_state.current_question}")
        if st.session_state.question_audio:
            st.audio(st.session_state.question_audio, format="audio/mpeg")
        elif st.session_state.question_audio_error:
            st.caption(f"语音播放不可用：{st.session_state.question_audio_error}")

    if not all_done:
        answer_mode = st.segmented_control(
            "回答方式",
            ["语音输入", "文字输入"],
            default="语音输入",
            key="answer_input_mode",
        )
        with st.container(border=True):
            if answer_mode == "语音输入":
                audio_in = st.audio_input("点击录制回答", key="answer_audio")
                if audio_in is not None:
                    audio_bytes = audio_in.getvalue()
                    st.audio(audio_bytes, format="audio/wav")
                    audio_digest = hashlib.sha256(audio_bytes).hexdigest()
                    if audio_digest == st.session_state.last_audio_digest:
                        st.caption("这段录音已经处理过，请录制下一段回答。")
                    else:
                        st.session_state.last_audio_digest = audio_digest
                        try:
                            with st.spinner("正在识别回答..."):
                                ans_text = audio2text(audio_bytes)
                        except Exception as exc:
                            st.error(str(exc))
                        else:
                            if not ans_text:
                                st.warning("没有识别到有效内容，请重新录制。")
                            else:
                                st.success(f"识别结果：{ans_text}")
                                if process_answer(ans_text, mode_cfg):
                                    st.rerun()
            else:
                with st.form("text_answer_form", clear_on_submit=True, border=False):
                    text_answer = st.text_area(
                        "输入文字回答",
                        height=150,
                        placeholder="在这里输入你的回答，提交后进入下一题。",
                        key="text_answer",
                    )
                    text_submitted = st.form_submit_button(
                        "提交回答",
                        type="primary",
                        key="submit_text_answer",
                        width="stretch",
                    )
                if text_submitted:
                    cleaned_answer = text_answer.strip()
                    if not cleaned_answer:
                        st.warning("请输入文字回答后再提交。")
                    elif process_answer(cleaned_answer, mode_cfg):
                        st.rerun()

    st.caption("结束后点击下方按钮生成完整复盘和面试记录。")
    if st.button(
        "结束面试并生成复盘",
        type="primary",
        key="finish_interview",
        width="stretch",
    ):
        if generate_review(mode_cfg):
            set_view("report")
            st.rerun()


def render_report() -> None:
    st.header("复盘报告")
    feedback = st.session_state.get("feedback")
    if not feedback:
        with st.container(border=True):
            st.markdown("### 还没有可查看的复盘")
            st.write("完成一轮面试后，系统会在这里生成结构化复盘。")
            if st.button("开始一轮面试", type="primary", key="report_empty_start"):
                go_to("setup")
        return

    duration_seconds = None
    if st.session_state.get("start_time") is not None:
        duration_seconds = int(max(0, time.time() - st.session_state.start_time))
    tags = st.session_state.get("last_tags", [])
    metric_cols = st.columns(3)
    metric_cols[0].metric("回答轮次", len(st.session_state.messages) // 2)
    metric_cols[1].metric("薄弱标签", len(tags))
    metric_cols[2].metric(
        "用时",
        f"{(duration_seconds or 0) // 60} 分钟",
    )

    job_match = st.session_state.get("job_match")
    if isinstance(job_match, JobMatchReport):
        with st.container(border=True):
            st.markdown("### 岗位匹配")
            match_cols = st.columns(3)
            match_cols[0].metric("匹配度", f"{job_match.match_score}/100")
            match_cols[1].metric("已匹配技能", len(job_match.matched_skills))
            match_cols[2].metric("缺失技能", len(job_match.missing_skills))
            if job_match.matched_skills:
                st.caption("已匹配：" + "、".join(job_match.matched_skills))
            if job_match.missing_skills:
                st.caption("需要补强：" + "、".join(job_match.missing_skills))
            if job_match.suggested_focus:
                st.caption("建议重点：" + "；".join(job_match.suggested_focus))

    if tags:
        st.caption("本轮薄弱标签")
        st.write("  ".join(tags))

    with st.container(border=True):
        st.markdown(feedback)

    if st.session_state.get("last_record_path"):
        st.caption(f"完整记录已保存：{st.session_state.last_record_path}")
        if st.session_state.get("last_record_markdown"):
            st.download_button(
                "下载完整面试记录",
                data=st.session_state.last_record_markdown.encode("utf-8"),
                file_name=Path(st.session_state.last_record_path).name,
                mime="text/markdown",
                key="download_interview_record",
                width="stretch",
            )

    action_left, action_right = st.columns(2)
    if action_left.button("再练一轮", type="primary", key="report_again"):
        reset_interview_state()
        st.rerun()
    if action_right.button("查看成长记录", key="report_growth"):
        go_to("growth")


def render_growth(mode_cfg: dict) -> None:
    st.header("成长记录")
    st.caption("查看弱项、历史面试和最近一次运行的技术信息。")

    st.subheader("分轮次薄弱统计")
    tabs = st.tabs(MODE_LIST)
    for idx, mode in enumerate(MODE_LIST):
        with tabs[idx]:
            mode_stats = st.session_state.global_weak_stats[mode]
            if mode_stats:
                df = pd.DataFrame(
                    list(mode_stats.items()),
                    columns=["标签", "次数"],
                ).sort_values("次数", ascending=False)
                st.dataframe(df, hide_index=True)
                if st.button(f"清空【{mode}】统计", key=f"clear_{mode}"):
                    st.session_state.global_weak_stats[mode] = {}
                    try:
                        save_global_weak_stats(st.session_state.global_weak_stats)
                    except Exception as exc:
                        st.error(f"保存薄弱统计失败：{exc}")
                    else:
                        st.rerun()
            else:
                st.caption("暂无薄弱记录")

    st.subheader("历史面试")
    sessions = list_session_files()
    if not sessions:
        st.caption("暂无历史记录")
    for session_file in sessions:
        try:
            saved = json.loads(session_file.read_text(encoding="utf-8"))
            saved_mode = saved["mode"]
            if saved_mode not in MODE_CONFIG:
                raise ValueError("未知面试轮次")
        except Exception:
            st.caption(f"跳过损坏记录：{session_file.name}")
            continue
        label = (
            f"{saved.get('time', '未知时间')}  {saved_mode}  "
            f"{saved.get('interview_type', '未知模式')}"
        )
        open_col, delete_col = st.columns([4, 1])
        if open_col.button(label, key=f"history_{session_file.stem}", width="stretch"):
            st.session_state.messages = saved.get("messages", [])
            st.session_state.feedback = saved.get("feedback")
            st.session_state.last_tags = saved.get("tags", [])
            st.session_state.job_description = saved.get("job_description", "")
            restored_match = saved.get("job_match") or {}
            st.session_state.job_match = (
                JobMatchReport.from_dict(restored_match) if restored_match else None
            )
            st.session_state.mode = saved_mode
            st.session_state.interview_type = saved.get(
                "interview_type", "闯关全真面试"
            )
            st.session_state.style = saved.get(
                "style", MODE_CONFIG[saved_mode]["default_style"]
            )
            st.session_state.current_stage_idx = 0
            st.session_state.stage_main_index = 0
            st.session_state.stage_followup_count = 0
            st.session_state.current_question = ""
            st.session_state.question_audio = None
            st.session_state.question_audio_error = None
            st.session_state.start_time = None
            st.session_state.timer_alert = False
            st.session_state.interview_started_at = saved.get("started_at")
            st.session_state.last_record_path = None
            st.session_state.last_record_markdown = None
            st.session_state.agent_run = None
            st.session_state.model_budget = default_usage_budget()
            st.session_state.consent_granted = saved.get("consent_granted", False)
            st.session_state.consent_at = saved.get("consent_at")
            st.session_state.retention_policy = saved.get("retention_policy", "standard")
            st.session_state.session_id = new_session_id()
            set_view("report" if saved.get("feedback") else "setup")
            st.rerun()
        if delete_col.button("删除", key=f"delete_{session_file.stem}"):
            session_file.unlink(missing_ok=True)
            markdown_name = "_".join(
                [
                    safe_filename_part(saved.get("started_at", "未知")),
                    safe_filename_part(saved.get("mode", "未知")),
                    safe_filename_part(saved.get("interview_type", "未知")),
                    safe_filename_part(saved.get("style", "未知")),
                ]
            ) + ".md"
            (tenant_record_dir() / markdown_name).unlink(missing_ok=True)
            st.rerun()

    with st.expander("最近一次运行的技术信息"):
        budget = st.session_state.get("model_budget")
        if budget is not None:
            st.caption(
                f"本轮 Token：{budget.used_tokens:,} / {budget.max_tokens:,}  "
                f"估算成本：{budget.used_cost:.4f} / {budget.max_cost:.2f}"
            )
        quota = TENANT_QUOTA_STORE.snapshot(current_tenant_id())
        st.caption(
            f"租户额度：{quota['used_tokens']:,} / {quota['max_tokens']:,} Token  "
            f"{quota['used_cost']:.4f} / {quota['max_cost']:.2f}"
        )
        agent_run = st.session_state.get("agent_run")
        if agent_run is not None:
            model_calls = [
                event for event in agent_run.events if event.event_type == "model.call"
            ]
            st.caption(f"模型调用：{len(model_calls)} 次  事件：{len(agent_run.events)} 条")
            for event in model_calls[-5:]:
                payload = event.payload
                st.caption(
                    f"{event.node}  {payload.get('model', 'unknown')}  "
                    f"{payload.get('latency_ms', 0)} ms"
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
else:
    render_growth(mode_cfg)

st.caption("InterviewLoop  结构化面试  证据化复盘  持续训练")
