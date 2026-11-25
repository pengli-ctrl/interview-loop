"""测试模块，覆盖演示模式相关行为和回归场景。"""
from interview_loop.services.demo import DEMO_ANSWER, build_demo_llm_response


def test_demo_question_is_stage_aware():
    """验证演示题按阶段生成且不会跨阶段。"""
    prompt = "当前主问题：第 2/3 个：项目架构与关键取舍"
    response = build_demo_llm_response(prompt, "请给出当前这一题")
    assert "2/3" in response
    assert "项目架构与关键取舍" in response
    assert "说明：" not in response


def test_demo_review_and_tags():
    """验证演示复核和标签。"""
    assert "演示复盘" in build_demo_llm_response("你是面试评审", "")
    assert build_demo_llm_response("", "只输出 JSON 数组") == '["RAG", "Temporal"]'
    assert "演示模式" in DEMO_ANSWER
