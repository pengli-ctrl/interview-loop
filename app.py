import hashlib
import json
import time
from pathlib import Path

import pandas as pd
import streamlit as st

st.set_page_config(page_title="全真大厂面试模拟器", layout="wide")

from interview_loop.config import (
    DEMO_MODE,
    GLOBAL_STATS_PATH,
    MODE_CONFIG,
    MODE_LIST,
    RECORD_DIR,
    SAVE_DIR,
    STYLE_LIST,
)
from interview_loop.core.flow import FlowAction, decide_next_step
from interview_loop.core.question_engine import (
    build_repair_prompt,
    build_similarity_fallback,
    build_stage_question_prompt,
    questions_too_similar,
)
from interview_loop.core.review import build_review_prompt, build_tag_prompt, parse_tags
from interview_loop.platform.agent_run import AgentRun
from interview_loop.platform.builtin_tools import build_default_tool_registry
from interview_loop.platform.model_gateway import ModelGateway, default_usage_budget
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

MODEL_GATEWAY = ModelGateway()
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
            "budget_used_tokens": budget.used_tokens if budget else None,
            "budget_used_cost": round(budget.used_cost, 6) if budget else None,
        },
    )


def record_run_error(error: Exception | str, node: str) -> None:
    agent_run = st.session_state.get("agent_run")
    if agent_run is None:
        return
    agent_run.record_event("run.error", node, {"error": str(error)[:500]})


# ===================== 持久化与初始化 =====================
def list_session_files() -> list[Path]:
    return _list_session_files(SAVE_DIR)


def save_global_weak_stats(stats: dict) -> None:
    save_stats(GLOBAL_STATS_PATH, stats)


def save_session(mode: str, messages: list, feedback: str, tags: list[str]) -> Path:
    started_at = st.session_state.get("interview_started_at") or time.strftime(
        "%Y-%m-%d_%H-%M-%S"
    )
    duration_seconds = None
    if st.session_state.get("start_time") is not None:
        duration_seconds = int(max(0, time.time() - st.session_state.start_time))

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
    )
    agent_run = st.session_state.get("agent_run")
    if agent_run is not None:
        data["agent_run"] = agent_run.to_dict()
    budget = st.session_state.get("model_budget")
    if budget is not None:
        data["model_usage"] = budget.to_dict()
    json_path = save_session_json(SAVE_DIR, data)
    markdown_path, markdown = TOOL_REGISTRY.execute(
        "record.export",
        permissions={"record:write"},
        record_dir=RECORD_DIR,
        data=data,
    ).output
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
    )
    result = MODEL_GATEWAY.complete(
        "question",
        prompt.system_prompt,
        "请给出当前这一题",
        budget=st.session_state.get("model_budget"),
    )
    record_model_call(result, "model.question")
    question = result.content
    if previous_question and last_answer and questions_too_similar(question, previous_question):
        repair_result = MODEL_GATEWAY.complete(
            "question",
            build_repair_prompt(prompt.system_prompt),
            "请重新给出一个不同的问题",
            budget=st.session_state.get("model_budget"),
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
        )
        record_model_call(result, "model.review")
        feedback = result.content
    except Exception as exc:
        record_run_error(exc, "model.review.failed")
        st.error(str(exc))
        return False

    st.session_state.feedback = feedback
    agent_run = st.session_state.get("agent_run")
    if agent_run is not None:
        agent_run.complete("interview.review")
    tags = extract_tags(feedback, tag_list)
    try:
        update_global_stats(st.session_state.mode, tags)
    except Exception as exc:
        st.warning(f"薄弱统计更新失败：{exc}")
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
                )
            except Exception as exc:
                record_run_error(exc, "model.question.failed")
                st.error(str(exc))
                return False
            st.session_state.current_stage_idx = next_stage_idx
            st.session_state.stage_main_index = 0
            st.session_state.stage_followup_count = 0
        else:
            question = "本次面试所有阶段完成，你可以说【结束面试】或点击 Finish 生成复盘。"
            st.session_state.current_stage_idx = len(mode_cfg["stage_list"])
            st.session_state.stage_main_index = 0
            st.session_state.stage_followup_count = 0
    else:
        try:
            question = get_weak_question(st.session_state.mode)
        except Exception as exc:
            st.error(str(exc))
            return False

    st.session_state.current_question = question
    if agent_run is not None:
        agent_run.record_event(
            "question.generated",
            "interview.question",
            {"question": question},
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
st.title("🎙️ 全真大厂面试模拟器｜闯关 + 专项双模式")

if DEMO_MODE:
    st.info("当前为演示模式：不调用 DeepSeek、ASR 或 TTS，可完整体验面试状态机和复盘流程。")

col0_1, col0_2, col0_3 = st.columns([1, 1, 1])
with col0_1:
    new_mode = st.selectbox(
        "👉 面试轮次",
        MODE_LIST,
        index=MODE_LIST.index(st.session_state.mode),
    )
    if new_mode != st.session_state.mode:
        st.session_state.mode = new_mode
        st.session_state.style = MODE_CONFIG[new_mode]["default_style"]
        reset_interview_state()
        st.rerun()

with col0_2:
    new_it = st.radio(
        "面试模式",
        ["闯关全真面试", "薄弱专项练习"],
        horizontal=True,
        index=0 if st.session_state.interview_type == "闯关全真面试" else 1,
    )
    if new_it != st.session_state.interview_type:
        st.session_state.interview_type = new_it
        reset_interview_state()
        st.rerun()

with col0_3:
    st.session_state.style = st.selectbox(
        "面试官风格",
        STYLE_LIST,
        index=STYLE_LIST.index(st.session_state.style),
    )

mode_cfg = MODE_CONFIG[st.session_state.mode]
st.markdown(f"✅ 当前轮次：**{st.session_state.mode}**｜风格：**{st.session_state.style}**")

if st.session_state.interview_type == "闯关全真面试":
    stages = mode_cfg["stage_list"]
    total_stage = len(stages)
    cur_idx = st.session_state.current_stage_idx
    if cur_idx < total_stage:
        cur_stage = stages[cur_idx]
        question_plan = cur_stage.get("question_plan") or cur_stage["pool"]
        main_total = max(1, len(question_plan))
        main_current = min(st.session_state.stage_main_index + 1, main_total)
        max_followups = max(0, int(cur_stage.get("max_followups", 0)))
        followup_text = (
            f"｜追问 {st.session_state.stage_followup_count}/{max_followups}"
            if max_followups
            else ""
        )
        st.progress(
            (cur_idx + 1) / total_stage,
            text=(
                f"进度：阶段 {cur_idx + 1}/{total_stage}｜【{cur_stage['name']}】"
                f"｜主问题 {main_current}/{main_total}{followup_text}"
            ),
        )
        if st.button("⏭️ 跳过当前阶段", help="直接跳到下一阶段"):
            next_stage_idx = st.session_state.current_stage_idx + 1
            st.session_state.current_stage_idx = next_stage_idx
            st.session_state.stage_main_index = 0
            st.session_state.stage_followup_count = 0
            st.session_state.current_question = ""
            st.session_state.question_audio = None
            st.session_state.question_audio_error = None

            if st.session_state.start_time is not None:
                if next_stage_idx >= total_stage:
                    st.session_state.current_question = (
                        "本次面试所有阶段完成，你可以点击 Finish 生成复盘。"
                    )
                    st.rerun()
                else:
                    try:
                        with st.spinner("正在生成下一阶段题目..."):
                            next_question = get_stage_question(
                                st.session_state.mode,
                                next_stage_idx,
                                query_resume(st.session_state.resume_retriever, ""),
                                st.session_state.global_weak_stats[st.session_state.mode],
                                0,
                                0,
                                False,
                            )
                    except Exception as exc:
                        st.error(str(exc))
                        st.session_state.start_time = None
                    else:
                        st.session_state.current_question = next_question
                        set_question_audio(next_question)
                        st.rerun()
            else:
                st.rerun()
    else:
        st.success("🎉 所有面试阶段全部走完！")

col_main, col_side = st.columns([2, 1])
with col_main:
    upload = st.file_uploader(
        "📄 上传简历（txt/md/pdf），RAG 个性化出题",
        type=["txt", "md", "pdf"],
        key="resume_upload",
    )

    if upload is None:
        if st.session_state.resume_signature is not None:
            st.session_state.resume_signature = None
            st.session_state.resume_retriever = None
            st.session_state.resume_name = None
            st.session_state.resume_chars = 0
            st.session_state.resume_error = None
            st.session_state.resume_rag_mode = None
    else:
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
            except Exception as exc:
                st.session_state.resume_error = str(exc)

        if st.session_state.resume_error:
            st.error(f"简历加载失败：{st.session_state.resume_error}")
        elif st.session_state.resume_retriever is not None:
            st.caption(
                f"已加载简历：{st.session_state.resume_name}｜"
                f"{st.session_state.resume_chars} 字符｜"
                f"检索模式：{st.session_state.resume_rag_mode}｜后续重跑不会重复解析"
            )
    if st.session_state.start_time is None:
        if st.button("▶️ 开始面试计时", key="start_interview"):
            if (
                st.session_state.interview_type == "闯关全真面试"
                and st.session_state.current_stage_idx >= len(mode_cfg["stage_list"])
            ):
                st.warning("所有阶段已完成，可以点击 Finish 生成复盘或开启新一轮")
            else:
                st.session_state.model_budget = default_usage_budget()
                agent_run = AgentRun(
                    metadata={
                        "mode": st.session_state.mode,
                        "interview_type": st.session_state.interview_type,
                        "style": st.session_state.style,
                    }
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
                    agent_run.record_event(
                        "question.generated",
                        "interview.question",
                        {"question": question},
                    )
                    st.session_state.agent_run = agent_run
                    set_question_audio(question)
                    st.rerun()
    else:
        render_interview_timer()

    if st.session_state.current_question:
        st.subheader("👨‍💼 面试官问题")
        st.markdown(f"**{st.session_state.current_question}**")
        if st.session_state.question_audio:
            st.audio(st.session_state.question_audio, format="audio/mpeg")
        elif st.session_state.question_audio_error:
            st.caption(f"语音播放不可用：{st.session_state.question_audio_error}")

        answer_mode = st.radio(
            "选择回答方式",
            ["🎤 语音输入", "⌨️ 文字输入"],
            index=0,
            horizontal=True,
            key="answer_input_mode",
        )

        if answer_mode == "🎤 语音输入":
            audio_in = st.audio_input("🎤 点击录制回答", key="answer_audio")
            if audio_in is not None:
                audio_bytes = audio_in.getvalue()
                st.audio(audio_bytes, format="audio/wav")
                audio_digest = hashlib.sha256(audio_bytes).hexdigest()
                if audio_digest == st.session_state.last_audio_digest:
                    st.caption("这段录音已经处理过；请重新录制下一段回答")
                else:
                    # 先标记已处理，避免 Streamlit 重跑时重复识别同一段录音。
                    st.session_state.last_audio_digest = audio_digest
                    try:
                        with st.spinner("正在识别回答..."):
                            ans_text = audio2text(audio_bytes)
                    except Exception as exc:
                        st.error(str(exc))
                    else:
                        if not ans_text:
                            st.warning("没有识别到有效内容，请重新录制")
                        else:
                            st.success(f"✅ 识别回答：{ans_text}")
                            if process_answer(ans_text, mode_cfg):
                                st.rerun()
        else:
            with st.form("text_answer_form", clear_on_submit=True, border=True):
                text_answer = st.text_area(
                    "⌨️ 输入文字回答",
                    height=140,
                    placeholder="在这里输入你的回答，提交后与语音回答流程完全一致。",
                    key="text_answer",
                )
                text_submitted = st.form_submit_button(
                    "提交文字回答",
                    type="primary",
                    key="submit_text_answer",
                )
            if text_submitted:
                cleaned_answer = text_answer.strip()
                if not cleaned_answer:
                    st.warning("请输入文字回答后再提交")
                elif process_answer(cleaned_answer, mode_cfg):
                    st.rerun()

        if st.button("✅ Finish 结束面试，生成复盘", type="primary", key="finish_interview"):
            if generate_review(mode_cfg):
                st.rerun()

    if st.session_state.feedback:
        st.markdown("---")
        st.subheader("📝 面试复盘报告")
        st.markdown(st.session_state.feedback)

    if st.session_state.get("last_record_path"):
        st.success(f"完整面试记录已保存：{st.session_state.last_record_path}")
        if st.session_state.get("last_record_markdown"):
            st.download_button(
                "⬇️ 下载本次面试记录",
                data=st.session_state.last_record_markdown.encode("utf-8"),
                file_name=Path(st.session_state.last_record_path).name,
                mime="text/markdown",
                key="download_interview_record",
            )

    if st.button("🔄 开启新一轮【当前轮次】面试", key="new_round"):
        reset_interview_state()
        st.rerun()
with col_side:
    st.subheader("本轮模型用量")
    budget = st.session_state.get("model_budget")
    agent_run = st.session_state.get("agent_run")
    if budget is not None:
        st.caption(
            f"Token: {budget.used_tokens:,} / {budget.max_tokens:,}  "
            f"估算成本(CNY): {budget.used_cost:.4f} / {budget.max_cost:.2f}"
        )
        model_calls = (
            [event for event in agent_run.events if event.event_type == "model.call"]
            if agent_run is not None
            else []
        )
        st.caption(f"已记录模型调用 {len(model_calls)} 次；成本按配置单价估算。")
        if model_calls:
            with st.expander("最近模型调用"):
                for event in model_calls[-5:]:
                    payload = event.payload
                    st.caption(
                        f"{event.node} | {payload.get('model', 'unknown')} | "
                        f"{payload.get('latency_ms', 0)} ms | "
                        f"{payload.get('attempts', 0)} 次尝试"
                    )

    st.subheader("📊 分轮次薄弱统计")
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
                if st.button(f"🗑️ 清空【{mode}】统计", key=f"clear_{mode}"):
                    st.session_state.global_weak_stats[mode] = {}
                    try:
                        save_global_weak_stats(st.session_state.global_weak_stats)
                    except Exception as exc:
                        st.error(f"保存薄弱统计失败：{exc}")
                    else:
                        st.rerun()
            else:
                st.write("暂无薄弱记录")

    st.subheader("📚 历史面试记录")
    st.session_state.session_list = list_session_files()
    for session_file in st.session_state.session_list:
        try:
            saved = json.loads(session_file.read_text(encoding="utf-8"))
            saved_mode = saved["mode"]
            if saved_mode not in MODE_CONFIG:
                raise ValueError("未知面试轮次")
        except Exception:
            st.caption(f"跳过损坏记录：{session_file.name}")
            continue

        label = (
            f"{saved.get('time', '未知时间')}｜{saved_mode}｜"
            f"{saved.get('interview_type', '未知模式')}"
        )
        if st.button(label, key=f"history_{session_file.stem}"):
            st.session_state.messages = saved.get("messages", [])
            st.session_state.feedback = saved.get("feedback")
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
            st.session_state.session_id = new_session_id()
            st.rerun()

st.caption(
    "全真面试模拟器｜60 分钟闯关流程、主问题与动态追问、文字/语音作答；"
    "专项模式专攻短板"
)