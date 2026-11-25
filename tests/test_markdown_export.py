"""测试模块，覆盖 Markdown 导出相关行为和回归场景。"""
from interview_loop.export.markdown import (
    build_markdown_record,
    format_duration,
    safe_filename_part,
    save_markdown_record,
)


def _record_data():
    """构造测试用会话记录数据。

    Returns:
        函数处理结果，类型为 未标注。

    """
    return {
        "started_at": "2026-11-25_10-00-00",
        "completed_at": "2026-11-25 10:30:00",
        "mode": "技术一面",
        "interview_type": "闯关全真面试",
        "style": "温和",
        "duration_seconds": 1800,
        "session_id": "session_test",
        "messages": [
            {"role": "interviewer", "content": "问题一"},
            {"role": "candidate", "content": "回答一"},
            {"role": "interviewer", "content": "问题二"},
            {"role": "candidate", "content": "回答二"},
        ],
        "feedback": "复盘报告",
        "tags": ["RAG", "Temporal"],
        "structured_report": {
            "overall_score": 7.2,
            "dimensions": [
                {"name": "architecture", "label": "架构设计", "score": 7.5, "weight": 0.3}
            ],
            "strengths": ["架构设计清晰"],
            "risks": ["缺少量化结果"],
            "action_plan": [
                {"priority": "P1", "action": "补充量化案例", "related_dimension": "architecture"}
            ],
            "evidence": [
                {
                    "dimension": "architecture",
                    "dimension_label": "架构设计",
                    "question": "如何设计？",
                    "answer_excerpt": "分层设计",
                    "score": 7.5,
                }
            ],
        },
    }


def test_markdown_pairs_questions_and_answers():
    """验证 Markdown 配对问题和回答。"""
    markdown = build_markdown_record(_record_data())
    assert markdown.count("**面试官：**") == 2
    assert markdown.count("**候选人：**") == 2
    assert "问题一" in markdown and "回答二" in markdown


def test_markdown_handles_unanswered_question():
    """验证Markdown处理未回答问题。"""
    data = _record_data()
    data["messages"] = [{"role": "interviewer", "content": "未回答的问题"}]
    markdown = build_markdown_record(data)
    assert "未回答的问题" in markdown
    assert "（未回答）" in markdown


def test_markdown_includes_review_and_tags():
    """验证Markdown包含复核和标签。"""
    markdown = build_markdown_record(_record_data())
    assert "## 表达结构参考评估" in markdown
    assert "表达结构参考分（启发式）：7.2/10" in markdown
    assert "## 面试复盘报告" in markdown
    assert "- RAG" in markdown


def test_filename_cleaning():
    """验证文件名清洗。"""
    assert safe_filename_part("a/b:c*?") == "a_b_c__"


def test_duration_formatting():
    """验证时长格式化。"""
    assert format_duration(3661) == "1小时1分1秒"
    assert format_duration(None) == "未记录"


def test_save_markdown_record(tmp_path):
    """验证保存Markdown记录。

    Args:
        tmp_path: `tmp_path` 输入参数，类型为 未标注。

    """
    path, markdown = save_markdown_record(tmp_path, _record_data())
    assert path.exists()
    assert path.name == "2026-11-25_10-00-00_技术一面_闯关全真面试_温和.md"
    assert path.read_text(encoding="utf-8") == markdown
