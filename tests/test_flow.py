"""测试模块，覆盖流程相关行为和回归场景。"""
from interview_loop.core.flow import (
    FlowAction,
    decide_next_step,
    is_explicit_end_request,
    should_generate_followup,
)

LONG_ANSWER = "我负责 RAG 检索链路和 Agent 编排平台，完成了限流、降级、幂等和容灾设计，并持续推进稳定性优化。"


def test_long_answer_allows_followup():
    """验证长回答允许追问。"""
    assert should_generate_followup(LONG_ANSWER, max_followups=1, followup_count=0)


def test_short_answer_skips_followup():
    """验证短回答跳过追问。"""
    assert not should_generate_followup("做过平台。", max_followups=2, followup_count=0)


def test_unknown_answer_skips_followup():
    """验证未知回答跳过追问。"""
    assert not should_generate_followup("这个我不知道。" * 10, max_followups=2, followup_count=0)


def test_followup_limit_is_respected():
    """验证追问上限判断被遵守。"""
    assert not should_generate_followup(LONG_ANSWER, max_followups=1, followup_count=1)


def test_decide_followup():
    """验证决定追问。"""
    decision = decide_next_step(main_count=2, main_index=0, followup_count=0, max_followups=1, answer=LONG_ANSWER, is_last_stage=False)
    assert decision.action is FlowAction.FOLLOW_UP
    assert (decision.main_index, decision.followup_count) == (0, 1)


def test_decide_next_main():
    """验证决定下一步主流程。"""
    decision = decide_next_step(main_count=2, main_index=0, followup_count=1, max_followups=1, answer=LONG_ANSWER, is_last_stage=False)
    assert decision.action is FlowAction.NEXT_MAIN
    assert (decision.main_index, decision.followup_count) == (1, 0)


def test_decide_next_stage():
    """验证决定下一步阶段。"""
    decision = decide_next_step(main_count=1, main_index=0, followup_count=0, max_followups=0, answer=LONG_ANSWER, is_last_stage=False)
    assert decision.action is FlowAction.NEXT_STAGE


def test_decide_complete():
    """验证决定完成。"""
    decision = decide_next_step(main_count=1, main_index=0, followup_count=0, max_followups=0, answer=LONG_ANSWER, is_last_stage=True)
    assert decision.action is FlowAction.COMPLETE


def test_explicit_end_request_requires_control_phrase():
    """验证显式结束请求需要控制短语。"""
    assert is_explicit_end_request("结束面试")
    assert is_explicit_end_request("请结束本轮面试。")
    assert not is_explicit_end_request("我之前结束面试后会复盘一下。")
