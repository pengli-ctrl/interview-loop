"""Report page presentation for InterviewLoop."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pandas as pd
import streamlit as st

from interview_loop.core.job_match import JobMatchReport
from interview_loop.evaluation.interview_report import InterviewReport
from interview_loop.export.markdown import format_duration
from interview_loop.ui.components import render_chips, render_score_card


def render_report_view(
    *,
    feedback: str | None,
    duration_seconds: int | None,
    tags: list[str],
    structured_report: InterviewReport | None,
    job_match: JobMatchReport | None,
    messages_count: int,
    demo_mode: bool,
    last_record_path: str | None,
    last_record_markdown: str | None,
    mode: str,
    interview_type: str,
    style: str,
    on_start: Callable[[], None],
    on_again: Callable[[], None],
    on_growth: Callable[[], None],
) -> None:
    st.header("复盘报告")
    if not feedback:
        with st.container(border=True):
            st.markdown("### 还没有可查看的复盘")
            st.write("完成一轮面试后，系统会在这里生成结构化复盘。")
            if st.button("开始一轮面试", type="primary", key="report_empty_start"):
                on_start()
        return

    render_chips(
        [
            ("轮次", mode),
            ("模式", interview_type),
            ("风格", style),
        ]
    )

    duration_text = "演示流程" if demo_mode else format_duration(duration_seconds)

    if isinstance(structured_report, InterviewReport):
        score_col, chart_col = st.columns([1, 2])
        with score_col:
            render_score_card(structured_report.overall_score)
            st.caption("启发式参考分，仅用于训练反馈，不等同于语义评分或录用结论。")
        with chart_col:
            chart_data = pd.DataFrame(
                [
                    {"维度": item.label, "得分": item.score}
                    for item in structured_report.dimensions
                ]
            )
            st.caption("维度参考分")
            st.bar_chart(
                chart_data,
                x="维度",
                y="得分",
                horizontal=True,
                alt="本次面试各能力维度参考分",
            )

        render_chips(
            [
                ("回答轮次", str(messages_count // 2)),
                ("薄弱标签", str(len(tags))),
                ("用时", duration_text),
            ]
        )
        if structured_report.action_plan:
            primary_action = structured_report.action_plan[0]
            with st.container(border=True):
                st.markdown(f"### 优先行动：{primary_action.action}")
                for action in structured_report.action_plan[1:]:
                    st.write(f"- **{action.priority}** {action.action}")
        with st.container(border=True):
            st.write(structured_report.summary)
            strength_col, risk_col = st.columns(2)
            with strength_col:
                st.markdown("#### 优势")
                for item in structured_report.strengths:
                    st.write(f"- {item}")
            with risk_col:
                st.markdown("#### 风险与不足")
                for item in structured_report.risks:
                    st.write(f"- {item}")
        with st.expander("查看回答证据"):
            for item in structured_report.evidence:
                st.markdown(f"**{item.dimension_label}**  {item.score}/10")
                st.caption(item.question)
                st.write(item.answer_excerpt)
    else:
        st.info("这是一条旧版面试记录，未包含结构化参考分；原复盘内容仍可正常查看。")
        render_chips(
            [
                ("回答轮次", str(messages_count // 2)),
                ("薄弱标签", str(len(tags))),
                ("用时", duration_text),
            ]
        )

    if isinstance(job_match, JobMatchReport):
        with st.expander("岗位匹配", expanded=False):
            job_match_value = (
                "未评分"
                if job_match.match_level == "unscored"
                else f"{job_match.match_score}/100"
            )
            render_chips(
                [
                    ("匹配度", job_match_value),
                    ("已匹配技能", str(len(job_match.matched_skills))),
                    ("缺失技能", str(len(job_match.missing_skills))),
                ]
            )
            if job_match.match_level == "unscored":
                st.caption("技能目录未覆盖该 JD，本次岗位匹配不评分。")
            if job_match.matched_skills:
                st.caption("已匹配：" + "、".join(job_match.matched_skills))
            if job_match.missing_skills:
                st.caption("需要补强：" + "、".join(job_match.missing_skills))
            if job_match.suggested_focus:
                st.caption("建议重点：" + "；".join(job_match.suggested_focus))

    if tags:
        st.caption("本轮薄弱标签")
        st.write("  ".join(tags))

    with st.expander("面试官总评（非评分）", expanded=False):
        st.markdown(feedback)

    if last_record_path:
        st.caption(f"完整记录已保存：{last_record_path}")
        if last_record_markdown:
            st.download_button(
                "下载完整面试记录",
                data=last_record_markdown.encode("utf-8"),
                file_name=Path(last_record_path).name,
                mime="text/markdown",
                key="download_interview_record",
                width="stretch",
            )

    action_left, action_right = st.columns(2)
    if action_left.button("再练一轮", type="primary", key="report_again"):
        on_again()
    if action_right.button("查看成长记录", key="report_growth"):
        on_growth()
