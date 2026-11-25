"""Streamlit 面试室页面模块，负责阶段进度、计时、问题、语音/文字回答和结束操作。"""

from __future__ import annotations

import hashlib
from collections.abc import Callable

import streamlit as st

from interview_loop.services.asr import audio2text
from interview_loop.ui.components import render_chips


def render_interview_view(
    mode_cfg: dict,
    *,
    render_timer: Callable[[], None],
    process_answer: Callable[[str, dict], bool],
    open_setup: Callable[[], None],
    confirm_finish: Callable[[dict], None],
) -> None:
    """渲染专注面试室页面。

    Args:
        mode_cfg: `mode_cfg` 输入参数，类型为 dict。
        render_timer: `render_timer` 关键字参数，类型为 Callable[[], None]。
        process_answer: `process_answer` 关键字参数，类型为 Callable[[str, dict], bool]。
        open_setup: `open_setup` 关键字参数，类型为 Callable[[], None]。
        confirm_finish: `confirm_finish` 关键字参数，类型为 Callable[[dict], None]。

    """
    st.header("面试室")
    stage_position = min(
        int(st.session_state.get("current_stage_idx", 0)),
        len(mode_cfg["stage_list"]) - 1,
    )
    render_chips(
        [
            ("轮次", st.session_state.mode),
            ("阶段", mode_cfg["stage_list"][stage_position]["name"]),
            ("风格", st.session_state.style),
        ]
    )
    if st.session_state.get("start_time") is None or not st.session_state.get("current_question"):
        with st.container(border=True):
            st.markdown("### 还没有进行中的面试")
            st.write("先完成面试设置，再进入专注面试模式。")
            if st.button("去设置面试", type="primary", key="interview_empty_setup"):
                open_setup()
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

    render_timer()

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
        key="finish_interview",
        width="content",
    ):
        confirm_finish(mode_cfg)
