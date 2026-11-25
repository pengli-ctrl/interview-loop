from interview_loop.core.review import build_review_prompt, build_tag_prompt, parse_tags


def test_parse_valid_tags():
    assert parse_tags('["RAG", "Temporal"]', ["RAG", "Temporal", "OTel"]) == ["RAG", "Temporal"]


def test_parse_filters_unknown_tags():
    assert parse_tags('["RAG", "Unknown"]', ["RAG"]) == ["RAG"]


def test_parse_invalid_json_returns_empty():
    assert parse_tags("not json", ["RAG"]) == []


def test_review_and_tag_prompts_contain_context():
    review = build_review_prompt("技术一面", "温和", ["RAG"], [{"role": "candidate", "content": "回答"}])
    tags = build_tag_prompt("不足：RAG", ["RAG", "Temporal"])
    assert "技术一面" in review and "回答" in review
    assert "RAG" in tags and "Temporal" in tags
