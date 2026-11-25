"""Growth history and trend page."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pandas as pd
import streamlit as st

from interview_loop.evaluation.interview_report import (
    build_progress_records,
    compare_weak_areas,
)
from interview_loop.export.markdown import build_markdown_record, safe_filename_part


def render_growth_view(
    *,
    mode_list: list[str],
    mode_config: dict,
    current_mode: str,
    weak_stats: dict,
    session_files: list[Path],
    record_dir: Path,
    save_weak_stats: Callable[[dict], None],
    open_session: Callable[[dict, Path], None],
    delete_session: Callable[[Path, Path, dict], None],
    budget,
    tenant_snapshot: dict,
    agent_run,
) -> None:
    st.header("成长记录")
    st.caption("查看弱项、历史面试和最近一次运行的技术信息。")

    st.subheader("分轮次薄弱统计")
    tabs = st.tabs(mode_list)
    for idx, mode in enumerate(mode_list):
        with tabs[idx]:
            mode_stats = weak_stats[mode]
            if mode_stats:
                frame = pd.DataFrame(
                    list(mode_stats.items()),
                    columns=["标签", "次数"],
                ).sort_values("次数", ascending=False)
                st.dataframe(frame, hide_index=True)
                if st.button(f"清空【{mode}】统计", key=f"clear_{mode}"):
                    weak_stats[mode] = {}
                    try:
                        save_weak_stats(weak_stats)
                    except Exception as exc:
                        st.error(f"保存薄弱统计失败：{exc}")
                    else:
                        st.rerun()
            else:
                st.caption("暂无薄弱记录")

    session_records = []
    for session_file in session_files:
        try:
            import json

            session_records.append(json.loads(session_file.read_text(encoding="utf-8")))
        except Exception:
            continue
    progress_records = build_progress_records(session_records, mode=current_mode)
    st.subheader("能力趋势")
    if len(progress_records) >= 2:
        trend_data = pd.DataFrame(
            [
                {
                    "训练次数": str(index),
                    "时间": item.time,
                    "表达结构参考分": item.overall_score,
                }
                for index, item in enumerate(progress_records, start=1)
            ]
        )
        st.line_chart(
            trend_data,
            x="训练次数",
            y="表达结构参考分",
            alt="按训练次序展示的表达结构参考分趋势",
        )
        st.caption("图中按训练次数展示，完整时间见下方历史记录。")
        change = compare_weak_areas(
            list(progress_records[-1].tags),
            list(progress_records[-2].tags),
        )
        st.caption("最近两次薄弱项变化")
        if change.new_areas:
            st.write("新增：" + "、".join(change.new_areas))
        if change.resolved_areas:
            st.write("已改善：" + "、".join(change.resolved_areas))
        if change.persistent_areas:
            st.write("持续存在：" + "、".join(change.persistent_areas))
    elif progress_records:
        current = progress_records[-1]
        st.metric("当前表达结构参考分", f"{current.overall_score:.1f}/10")
        st.progress(
            min(1.0, max(0.0, current.overall_score / 10)),
            text="完成第 2 轮面试后将显示趋势线和薄弱项变化。",
        )
    else:
        st.caption("暂无表达结构参考分；完成新一轮面试后会自动生成。")

    st.subheader("历史面试")
    if not session_files:
        st.caption("暂无历史记录")
    for session_file in session_files:
        try:
            import json

            saved = json.loads(session_file.read_text(encoding="utf-8"))
            saved_mode = saved["mode"]
            if saved_mode not in mode_config:
                raise ValueError("未知面试轮次")
        except Exception:
            st.caption(f"跳过损坏记录：{session_file.name}")
            continue
        label = (
            f"{saved.get('time', '未知时间')}  {saved_mode}  "
            f"{saved.get('interview_type', '未知模式')}"
        )
        markdown_name = "_".join(
            [
                safe_filename_part(saved.get("started_at", "未知")),
                safe_filename_part(saved.get("mode", "未知")),
                safe_filename_part(saved.get("interview_type", "未知")),
                safe_filename_part(saved.get("style", "未知")),
            ]
        ) + ".md"
        markdown_path = record_dir / markdown_name
        markdown_content = (
            markdown_path.read_text(encoding="utf-8")
            if markdown_path.is_file()
            else build_markdown_record(saved)
        )
        open_col, download_col, delete_col = st.columns([4, 1, 1])
        if open_col.button(label, key=f"history_{session_file.stem}", width="stretch"):
            open_session(saved, session_file)
        download_col.download_button(
            "下载",
            data=markdown_content.encode("utf-8"),
            file_name=markdown_name,
            mime="text/markdown",
            key=f"download_history_{session_file.stem}",
            width="stretch",
        )
        if delete_col.button("删除", key=f"delete_{session_file.stem}"):
            st.session_state.delete_confirm_id = session_file.stem
            st.rerun()
        if st.session_state.get("delete_confirm_id") == session_file.stem:
            st.warning("删除后将同时移除 JSON 会话和 Markdown 记录，且无法恢复。")
            confirm_col, cancel_col = st.columns(2)
            if confirm_col.button(
                "确认删除",
                type="primary",
                key=f"confirm_delete_{session_file.stem}",
                width="stretch",
            ):
                delete_session(session_file, markdown_path, saved)
            if cancel_col.button(
                "取消",
                key=f"cancel_delete_{session_file.stem}",
                width="stretch",
            ):
                st.session_state.delete_confirm_id = None
                st.rerun()

    with st.expander("最近一次运行的技术信息"):
        if budget is not None:
            st.caption(
                f"本轮 Token：{budget.used_tokens:,} / {budget.max_tokens:,}  "
                f"估算成本：{budget.used_cost:.4f} / {budget.max_cost:.2f}"
            )
        st.caption(
            f"租户额度：{tenant_snapshot['used_tokens']:,} / "
            f"{tenant_snapshot['max_tokens']:,} Token  "
            f"{tenant_snapshot['used_cost']:.4f} / {tenant_snapshot['max_cost']:.2f}"
        )
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
