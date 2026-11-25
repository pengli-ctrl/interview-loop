"""测试模块，覆盖问题引擎相关行为和回归场景。"""
from interview_loop.core.question_engine import (
    build_similarity_fallback,
    build_stage_question_prompt,
    questions_too_similar,
)


def test_identical_questions_are_similar():
    """验证完全相同的问题判定为相似。"""
    assert questions_too_similar("请介绍项目架构", "请介绍项目架构")


def test_punctuation_only_difference_is_similar():
    """验证仅标点不同的问题判定为相似。"""
    assert questions_too_similar("请介绍项目架构。", "请介绍项目架构")


def test_different_questions_are_not_similar():
    """验证不同问题判定为不相似。"""
    assert not questions_too_similar("请介绍你的技术方向", "请说明故障排查链路")


def test_stage_prompt_contains_topic_and_stage():
    """验证阶段提示词包含主题和阶段。"""
    stage = {"name": "项目深挖", "desc": "项目架构、实现、难点", "question_plan": ["项目架构", "关键难点"], "max_followups": 2}
    prompt = build_stage_question_prompt(mode="技术一面", style="温和", stage=stage, resume_ctx="负责 RAG 平台", weak_stats={"RAG": 2}, main_index=1, followup_index=1, is_followup=True, previous_question="项目架构是什么？", last_answer="使用 BM25 和向量检索。", job_ctx="缺失技能：Kubernetes；风险：缺少量化结果")
    assert prompt.current_topic == "关键难点"
    assert "项目深挖" in prompt.system_prompt
    assert "候选人回答" in prompt.system_prompt
    assert "缺失技能：Kubernetes" in prompt.system_prompt


def test_similarity_fallback_uses_answer_and_topic():
    """验证相似度兜底追问使用回答和主题。"""
    fallback = build_similarity_fallback("项目架构", "我负责 RAG 平台和检索链路")
    assert "项目架构" in fallback
    assert "RAG" in fallback
