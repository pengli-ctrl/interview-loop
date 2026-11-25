"""Streamlit 管理控制台页面模块，负责展示场景、模型、工具、AgentRun 和评估指标。"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from interview_loop.admin.control_plane import (
    format_local_time,
    format_quality_thresholds,
    format_quota_snapshot,
    format_rag_thresholds,
    model_profile_rows,
    quality_metrics,
    recent_runs,
    run_rows,
    scenario_rows,
    tool_rows,
)
from interview_loop.platform.run_repository import SQLiteAgentRunRepository
from interview_loop.ui.components import render_metric_grid


def render_admin_view(
    *,
    registry,
    tool_registry,
    model_gateway,
    tenant_quota_store,
    base_dir: Path,
    db_path: Path,
    rag_metrics: dict,
    tenant_id: str,
) -> None:
    """渲染只读平台控制台。

    Args:
        registry: `registry` 关键字参数，类型为 未标注。
        tool_registry: `tool_registry` 关键字参数，类型为 未标注。
        model_gateway: `model_gateway` 关键字参数，类型为 未标注。
        tenant_quota_store: `tenant_quota_store` 关键字参数，类型为 未标注。
        base_dir: `base_dir` 关键字参数，类型为 Path。
        db_path: `db_path` 关键字参数，类型为 Path。
        rag_metrics: `rag_metrics` 关键字参数，类型为 dict。
        tenant_id: `tenant_id` 关键字参数，类型为 str。

    """
    st.header("平台控制台")
    st.caption("本地只读控制面：展示真实场景、模型、工具、运行轨迹和评估数据。")

    scenarios = registry.list_scenarios()
    tools = tool_registry.list_tools()
    quality = quality_metrics(base_dir / "datasets" / "quality_golden.json")
    repository = SQLiteAgentRunRepository(db_path)
    runs = recent_runs(repository, limit=20)
    current_run = st.session_state.get("agent_run")
    if current_run is not None and all(run.run_id != current_run.run_id for run in runs):
        runs.insert(0, current_run)

    render_metric_grid(
        [
            ("场景包", str(len(scenarios))),
            ("工具", str(len(tools))),
            ("最近 AgentRun", str(len(runs))),
            ("质量门禁", "通过" if quality["passed"] else "失败"),
        ]
    )

    tabs = st.tabs(["场景", "模型路由", "工具权限", "AgentRun / Trace", "评估指标"])
    with tabs[0]:
        st.subheader("场景目录")
        st.dataframe(pd.DataFrame(scenario_rows(registry)), hide_index=True)

    with tabs[1]:
        st.subheader("模型路由与预算")
        st.dataframe(pd.DataFrame(model_profile_rows(model_gateway)), hide_index=True)
        breaker = model_gateway._breaker_policy
        quota = tenant_quota_store.quota
        st.caption(
            f"熔断阈值：{breaker.failure_threshold} 次  "
            f"冷却：{breaker.cooldown_seconds:g} 秒"
        )
        st.caption(
            f"租户额度：{quota.max_tokens:,} Token / {quota.max_cost:.2f}  "
            f"窗口 {quota.window_seconds:g} 秒"
        )
        st.caption(
            "当前租户用量："
            + format_quota_snapshot(tenant_quota_store.snapshot(tenant_id))
        )

    with tabs[2]:
        st.subheader("工具目录与权限")
        st.dataframe(pd.DataFrame(tool_rows(tool_registry)), hide_index=True)

    with tabs[3]:
        st.subheader("最近 AgentRun")
        if not runs:
            st.caption("暂无 AgentRun。可通过 API 或开始一次面试生成。")
        else:
            st.dataframe(pd.DataFrame(run_rows(runs)), hide_index=True)
            selected_id = st.selectbox(
                "查看运行轨迹",
                [run.run_id for run in runs],
                key="admin_run_selector",
            )
            selected_run = next(run for run in runs if run.run_id == selected_id)
            st.caption(
                f"Trace ID：{selected_run.trace_id}  状态：{selected_run.status.value}"
            )
            if selected_run.events:
                st.dataframe(
                    pd.DataFrame(
                        [
                            {
                                "事件": event.event_type,
                                "节点": event.node,
                                "耗时ms": event.duration_ms,
                                "时间": format_local_time(event.created_at),
                                "Payload": event.payload,
                            }
                            for event in selected_run.events
                        ]
                    ),
                    hide_index=True,
                )
            else:
                st.caption("该 Run 暂无事件。")

    with tabs[4]:
        st.subheader("RAG 检索指标")
        render_metric_grid(
            [
                ("Precision@K", f"{rag_metrics['precision']:.3f}"),
                ("Recall@K", f"{rag_metrics['recall']:.3f}"),
                ("MRR", f"{rag_metrics['mrr']:.3f}"),
                ("Hit Rate", f"{rag_metrics['hit_rate']:.3f}"),
            ]
        )
        st.caption(
            f"黄金用例：{rag_metrics['case_count']}  "
            + format_rag_thresholds(rag_metrics["thresholds"])
        )
        st.subheader("模型输出质量校准")
        render_metric_grid(
            [
                ("加权 MAE", f"{quality['weighted_mae']:.3f}"),
                ("最大用例误差", f"{quality['max_case_mae']:.3f}"),
                ("人工复核", "通过" if quality["human_review_passed"] else "失败"),
            ]
        )
        st.caption("质量阈值：" + format_quality_thresholds(quality["thresholds"]))
