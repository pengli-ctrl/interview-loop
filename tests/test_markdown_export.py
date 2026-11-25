from interview_loop.export.markdown import (
    build_markdown_record,
    format_duration,
    safe_filename_part,
    save_markdown_record,
)


def _record_data():
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
    }


def test_markdown_pairs_questions_and_answers():
    markdown = build_markdown_record(_record_data())
    assert markdown.count("**面试官：**") == 2
    assert markdown.count("**候选人：**") == 2
    assert "问题一" in markdown and "回答二" in markdown


def test_markdown_handles_unanswered_question():
    data = _record_data()
    data["messages"] = [{"role": "interviewer", "content": "未回答的问题"}]
    markdown = build_markdown_record(data)
    assert "未回答的问题" in markdown
    assert "（未回答）" in markdown


def test_markdown_includes_review_and_tags():
    markdown = build_markdown_record(_record_data())
    assert "## 面试复盘报告" in markdown
    assert "- RAG" in markdown


def test_filename_cleaning():
    assert safe_filename_part("a/b:c*?") == "a_b_c__"


def test_duration_formatting():
    assert format_duration(3661) == "1小时1分1秒"
    assert format_duration(None) == "未记录"


def test_save_markdown_record(tmp_path):
    path, markdown = save_markdown_record(tmp_path, _record_data())
    assert path.exists()
    assert path.name == "2026-11-25_10-00-00_技术一面_闯关全真面试_温和.md"
    assert path.read_text(encoding="utf-8") == markdown
