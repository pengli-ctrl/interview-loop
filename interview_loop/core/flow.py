"""确定性面试流程模块，负责追问、主问题、阶段推进和结束决策。"""
import re
from dataclasses import dataclass
from enum import Enum

MIN_FOLLOWUP_ANSWER_CHARS = 40
NO_FOLLOWUP_KEYWORDS = ("不知道", "没做过", "跳过", "不了解", "不会")


class FlowAction(Enum):
    """面试流程的下一步动作枚举。"""
    FOLLOW_UP = "follow_up"
    NEXT_MAIN = "next_main"
    NEXT_STAGE = "next_stage"
    COMPLETE = "complete"


@dataclass(frozen=True)
class FlowDecision:
    """面试流程下一步决策。"""
    action: FlowAction
    main_index: int
    followup_count: int


def should_generate_followup(
    answer: str,
    max_followups: int,
    followup_count: int,
) -> bool:
    """判断当前回答是否应触发追问。

    Args:
        answer: `answer` 输入参数，类型为 str。
        max_followups: `max_followups` 输入参数，类型为 int。
        followup_count: `followup_count` 输入参数，类型为 int。

    Returns:
        函数处理结果，类型为 bool。

    """
    if followup_count >= max(0, int(max_followups)):
        return False
    cleaned = answer.strip()
    if len(cleaned) < MIN_FOLLOWUP_ANSWER_CHARS:
        return False
    return not any(keyword in cleaned for keyword in NO_FOLLOWUP_KEYWORDS)


def decide_next_step(
    *,
    main_count: int,
    main_index: int,
    followup_count: int,
    max_followups: int,
    answer: str,
    is_last_stage: bool,
) -> FlowDecision:
    """根据题目计划和回答决定下一步动作。

    Args:
        main_count: `main_count` 关键字参数，类型为 int。
        main_index: `main_index` 关键字参数，类型为 int。
        followup_count: `followup_count` 关键字参数，类型为 int。
        max_followups: `max_followups` 关键字参数，类型为 int。
        answer: `answer` 关键字参数，类型为 str。
        is_last_stage: `is_last_stage` 关键字参数，类型为 bool。

    Returns:
        函数处理结果，类型为 FlowDecision。

    """
    main_count = max(1, int(main_count))
    main_index = min(max(0, int(main_index)), main_count - 1)

    if should_generate_followup(answer, max_followups, followup_count):
        return FlowDecision(
            action=FlowAction.FOLLOW_UP,
            main_index=main_index,
            followup_count=followup_count + 1,
        )

    next_main_index = main_index + 1
    if next_main_index < main_count:
        return FlowDecision(
            action=FlowAction.NEXT_MAIN,
            main_index=next_main_index,
            followup_count=0,
        )

    if is_last_stage:
        return FlowDecision(
            action=FlowAction.COMPLETE,
            main_index=0,
            followup_count=0,
        )

    return FlowDecision(
        action=FlowAction.NEXT_STAGE,
        main_index=0,
        followup_count=0,
    )


END_REQUEST_PHRASES = {
    "结束面试",
    "结束本轮面试",
    "结束面试并生成复盘",
    "本次面试到此结束",
    "面试结束",
    "请结束面试",
    "请结束本轮面试",
    "结束面试吧",
}


def is_explicit_end_request(answer: str) -> bool:
    """判断回答是否为明确的结束控制短语。

    Args:
        answer: `answer` 输入参数，类型为 str。

    Returns:
        函数处理结果，类型为 bool。

    """
    cleaned = re.sub(r"[\s,.!?，。！？、]+", "", str(answer or ""))
    return cleaned in END_REQUEST_PHRASES
