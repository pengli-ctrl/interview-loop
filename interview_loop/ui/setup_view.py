"""Streamlit 面试设置页面模块，负责三步向导、JD/简历上下文、授权和开始面试。"""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable

import streamlit as st

from interview_loop.config import MODE_CONFIG, MODE_LIST, STYLE_LIST
from interview_loop.core.job_match import (
    JobDescriptionError,
    JobMatchReport,
    assess_job_match,
    load_default_skill_catalog,
)
from interview_loop.rag.resume import extract_resume_text
from interview_loop.rag.retriever import build_rag
from interview_loop.ui.components import RETENTION_OPTIONS, render_chips

SKILL_CATALOG = load_default_skill_catalog()


def render_setup_view(
    mode_cfg: dict,
    *,
    reset_interview_state: Callable[[], None],
    clear_resume_state: Callable[[], None],
    start_interview: Callable[[dict], None],
    continue_interview: Callable[[], None],
) -> None:
    """渲染三步面试设置向导。

    Args:
        mode_cfg: `mode_cfg` 输入参数，类型为 dict。
        reset_interview_state: `reset_interview_state` 关键字参数，类型为 Callable[[], None]。
        clear_resume_state: `clear_resume_state` 关键字参数，类型为 Callable[[], None]。
        start_interview: `start_interview` 关键字参数，类型为 Callable[[dict], None]。
        continue_interview: `continue_interview` 关键字参数，类型为 Callable[[], None]。

    Raises:
        ValueError: 当输入、状态或外部依赖不满足要求时抛出 ValueError。

    """
    st.header("设置一次面试")
    st.caption("先确定目标，再补充简历和授权信息。")

    if st.session_state.get("start_time") is not None and not st.session_state.get("feedback"):
        with st.container(border=True):
            st.markdown("### 当前面试尚未结束")
            st.write("继续当前面试，或新建一轮训练。")
            col_left, col_right = st.columns(2)
            if col_left.button("继续面试", type="primary", key="setup_continue_interview"):
                continue_interview()
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
            st.caption(
                f"当前技能目录 v{SKILL_CATALOG.version}，覆盖 "
                f"{len(SKILL_CATALOG.skills)} 个技术关键词。"
                "目录外的 JD 会标记为“未评分”，但不会阻断面试。"
            )
            cleaned_jd = jd_value.strip()
            if cleaned_jd != st.session_state.get("job_description", ""):
                st.session_state.job_description = cleaned_jd
                st.session_state.job_match = None
            upload = st.file_uploader(
                "上传简历（可选）",
                type=["txt", "md", "pdf"],
                key=f"resume_upload_{st.session_state.resume_upload_version}",
            )
            if upload is not None:
                file_bytes = upload.getvalue()
                signature = hashlib.sha256(file_bytes).hexdigest()
                if signature != st.session_state.resume_signature:
                    clear_resume_state()
                    st.session_state.resume_signature = signature
                    st.session_state.resume_name = upload.name
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
            elif st.session_state.resume_signature is not None:
                clear_resume_state()
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
                match_value = (
                    "未评分"
                    if saved_match.match_level == "unscored"
                    else f"{saved_match.match_score}/100"
                )
                render_chips(
                    [
                        ("匹配度", match_value),
                        ("已匹配", str(len(saved_match.matched_skills))),
                        ("待补强", str(len(saved_match.missing_skills))),
                    ]
                )
                if saved_match.match_level == "unscored":
                    st.caption("该 JD 不在当前技能目录内，本次不计算匹配分。")
                elif saved_match.missing_skills:
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
            render_chips(
                [
                    ("轮次", st.session_state.mode),
                    ("模式", st.session_state.interview_type),
                    ("风格", st.session_state.style),
                ]
            )
            current_match = st.session_state.get("job_match")
            if isinstance(current_match, JobMatchReport):
                st.markdown("#### 岗位匹配")
                current_match_value = (
                    "未评分"
                    if current_match.match_level == "unscored"
                    else f"{current_match.match_score}/100"
                )
                render_chips(
                    [
                        ("匹配度", current_match_value),
                        ("已匹配", str(len(current_match.matched_skills))),
                        ("待补强", str(len(current_match.missing_skills))),
                    ]
                )
                if current_match.match_level == "unscored":
                    st.caption("技能目录未覆盖该 JD，本次不计算匹配分，面试将使用通用技术上下文。")
                elif current_match.missing_skills:
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
            retention_labels = list(RETENTION_OPTIONS.values())
            current_retention = RETENTION_OPTIONS.get(
                st.session_state.retention_policy,
                RETENTION_OPTIONS["standard"],
            )
            selected_retention = st.selectbox(
                "数据保留策略",
                retention_labels,
                index=retention_labels.index(current_retention),
                help="临时=1天，标准=30天，延长=365天",
                key="retention_policy_select",
            )
            st.session_state.retention_policy = next(
                key for key, label in RETENTION_OPTIONS.items()
                if label == selected_retention
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
                    start_interview(mode_cfg)
