"""Dashboard page presentation."""

from __future__ import annotations

from collections.abc import Callable

import streamlit as st

from interview_loop.ui.components import render_metric_grid


def render_dashboard_view(
    *,
    sessions: list,
    latest: dict | None,
    weak_items: int,
    current_mode: str,
    pending_draft: dict | None,
    on_start: Callable[[], None],
    on_growth: Callable[[], None],
    on_report: Callable[[], None],
    on_restore: Callable[[], None],
    on_discard: Callable[[], None],
) -> None:
    st.title("InterviewLoop")
    st.caption("把一次面试练习，变成持续可见的能力成长。")

    if isinstance(pending_draft, dict):
        with st.container(border=True):
            st.markdown("## 发现未完成的面试")
            st.write(
                f"{pending_draft.get('mode', '未知轮次')} · "
                f"已完成 {len(pending_draft.get('messages', [])) // 2} 轮回答 · "
                f"最后更新 {pending_draft.get('updated_at', '未记录')}"
            )
            st.caption(f"当前问题：{pending_draft.get('current_question', '未记录')}")
            recovery_left, recovery_right = st.columns(2)
            if recovery_left.button(
                "恢复面试",
                type="primary",
                key="restore_interview_draft",
                width="stretch",
            ):
                on_restore()
            if recovery_right.button(
                "放弃草稿",
                key="discard_interview_draft",
                width="stretch",
            ):
                on_discard()

    with st.container(border=True):
        st.markdown("## 今天练什么？")
        st.write(
            "选择目标岗位和面试形式，完成一次完整模拟。结束后自动生成复盘、"
            "薄弱项和下一步训练建议。"
        )
        action_left, action_right = st.columns([1, 1])
        start_button_type = "secondary" if isinstance(pending_draft, dict) else "primary"
        if action_left.button(
            "开始一次面试",
            type=start_button_type,
            key="dashboard_start",
            width="stretch",
        ):
            on_start()
        if action_right.button(
            "查看成长记录",
            key="dashboard_growth",
            width="stretch",
        ):
            on_growth()

    latest_score = None
    if latest:
        latest_score = (latest.get("structured_report") or {}).get("overall_score")
    if sessions:
        render_metric_grid(
            [
                ("历史训练", str(len(sessions))),
                ("当前轮次", current_mode),
                (
                    "最近参考分",
                    f"{float(latest_score):.1f}/10" if latest_score is not None else "暂无",
                ),
                ("弱项记录", str(weak_items)),
            ]
        )
    else:
        with st.container(border=True):
            st.markdown("### 还没有训练记录")
            st.write("建议先完成一次完整模拟，系统会在结束后生成参考分、复盘和成长记录。")
            st.caption("首次练习建议：选择一个目标岗位，补充 JD 和简历，完成 3–5 轮回答后生成复盘。")

    st.subheader("训练入口")
    card_cols = st.columns(3)
    with card_cols[0].container(border=True, height="stretch"):
        st.markdown("#### 定向模拟")
        st.caption("按岗位轮次和风格完成一次结构化面试。")
        if st.button("进入设置", key="dashboard_card_setup", width="stretch"):
            on_start()
    with card_cols[1].container(border=True, height="stretch"):
        st.markdown("#### 最近复盘")
        if latest and latest.get("feedback"):
            st.caption(str(latest.get("time", "最近一次面试")))
            if st.button("打开报告", key="dashboard_card_report", width="stretch"):
                on_report()
        else:
            st.caption("完成一次面试后，这里会显示最近复盘。")
    with card_cols[2].container(border=True, height="stretch"):
        st.markdown("#### 能力趋势")
        st.caption("查看历史记录、重复弱项和训练变化。")
        if st.button("查看成长", key="dashboard_card_growth", width="stretch"):
            on_growth()
