"""Streamlit 通用组件模块，负责 CSS、chips、指标网格和评分卡片。"""

from __future__ import annotations

import html

import streamlit as st

RETENTION_OPTIONS = {
    "ephemeral": "临时（1 天）",
    "standard": "标准（30 天）",
    "extended": "延长（365 天）",
}


def inject_ui_css() -> None:
    """注入 InterviewLoop 的全局 UI 样式。"""
    st.markdown(
        """
        <style>
        .il-chip-row { display: flex; flex-wrap: wrap; gap: 0.5rem; margin: 0.25rem 0 1rem; }
        .il-chip {
          display: inline-flex; align-items: center; gap: 0.35rem;
          padding: 0.34rem 0.72rem; border: 1px solid #dbe4f0; border-radius: 999px;
          background: #f7f9fc; color: #475569; font-size: 0.84rem; line-height: 1.2;
        }
        .il-chip b { color: #0f172a; font-weight: 650; }
        .il-timer-row { display: flex; justify-content: flex-end; margin: 0.1rem 0 0.65rem; }
        .il-timer-pill {
          display: inline-flex; align-items: center; gap: 0.35rem;
          padding: 0.36rem 0.76rem; border-radius: 999px;
          background: #eff6ff; color: #1d4ed8; border: 1px solid #bfdbfe;
          font-variant-numeric: tabular-nums; font-weight: 650; font-size: 0.92rem;
        }
        .il-score-card {
          padding: 1rem 1.15rem; border-radius: 16px; background: #eff6ff;
          border: 1px solid #bfdbfe;
        }
        .il-score-label { color: #475569; font-size: 0.84rem; font-weight: 600; }
        .il-score-value {
          color: #1d4ed8; font-size: 3rem; line-height: 1.1; font-weight: 720;
          font-variant-numeric: tabular-nums;
        }
        .il-score-value span { color: #64748b; font-size: 1rem; font-weight: 550; }
        [data-testid="stSidebar"] [role="radiogroup"] { gap: 0.25rem; }
        [data-testid="stSidebar"] [role="radiogroup"] label {
          width: 100%; padding: 0.45rem 0.65rem; border-radius: 10px;
          transition: background 120ms ease;
        }
        [data-testid="stSidebar"] [role="radiogroup"] label:hover {
          background: #eef2f7;
        }
        [data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) {
          background: #e8f0ff; color: #1d4ed8; font-weight: 650;
        }
        [data-testid="stSidebar"] [role="radiogroup"] label[data-testid="stRadioOption"] > div > div:first-child {
          display: none !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_chips(items: list[tuple[str, str]]) -> None:
    """渲染一组轻量信息标签。

    Args:
        items: `items` 输入参数，类型为 list[tuple[str, str]]。

    """
    chips = "".join(
        f'<span class="il-chip"><b>{html.escape(str(label))}</b>'
        f"{html.escape(str(value))}</span>"
        for label, value in items
    )
    st.markdown(f'<div class="il-chip-row">{chips}</div>', unsafe_allow_html=True)


def render_metric_grid(items: list[tuple[str, str]]) -> None:
    """按两列网格渲染指标。

    Args:
        items: `items` 输入参数，类型为 list[tuple[str, str]]。

    """
    for start in range(0, len(items), 2):
        columns = st.columns(2)
        for column, (label, value) in zip(columns, items[start : start + 2]):
            column.metric(label, value)


def render_score_card(score: float) -> None:
    """渲染表达结构参考分卡片。

    Args:
        score: `score` 输入参数，类型为 float。

    """
    st.markdown(
        '<div class="il-score-card">'
        '<div class="il-score-label">表达结构参考分</div>'
        f'<div class="il-score-value">{score:.1f}<span>/10</span></div>'
        "</div>",
        unsafe_allow_html=True,
    )
