"""测试模块，覆盖复核相关行为和回归场景。"""
from interview_loop.core.review import (
    build_review_prompt,
    build_tag_prompt,
    parse_tags,
    strip_numeric_scores,
)


def test_parse_valid_tags():
    """验证解析有效标签。"""
    assert parse_tags('["RAG", "Temporal"]', ["RAG", "Temporal", "OTel"]) == ["RAG", "Temporal"]


def test_parse_filters_unknown_tags():
    """验证解析过滤未知标签。"""
    assert parse_tags('["RAG", "Unknown"]', ["RAG"]) == ["RAG"]


def test_parse_invalid_json_returns_empty():
    """验证解析无效JSON返回空。"""
    assert parse_tags("not json", ["RAG"]) == []


def test_review_and_tag_prompts_contain_context():
    """验证复盘和标签提示词包含上下文。"""
    review = build_review_prompt("技术一面", "温和", ["RAG"], [{"role": "candidate", "content": "回答"}])
    tags = build_tag_prompt("不足：RAG", ["RAG", "Temporal"])
    assert "技术一面" in review and "回答" in review
    assert "RAG" in tags and "Temporal" in tags


def test_strip_numeric_scores_removes_duplicate_score_claims():
    """验证数字评分清洗移除重复评分声明。"""
    review = "总评：结构清晰。\n- 评分：8/10\n综合得分 9/10，建议继续练习。"
    cleaned = strip_numeric_scores(review)
    assert "8/10" not in cleaned
    assert "9/10" not in cleaned
    assert "结构清晰" in cleaned
