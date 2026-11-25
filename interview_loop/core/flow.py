from dataclasses import dataclass
from enum import Enum

MIN_FOLLOWUP_ANSWER_CHARS = 40
NO_FOLLOWUP_KEYWORDS = ("不知道", "没做过", "跳过", "不了解", "不会")


class FlowAction(Enum):
    FOLLOW_UP = "follow_up"
    NEXT_MAIN = "next_main"
    NEXT_STAGE = "next_stage"
    COMPLETE = "complete"


@dataclass(frozen=True)
class FlowDecision:
    action: FlowAction
    main_index: int
    followup_count: int


def should_generate_followup(
    answer: str,
    max_followups: int,
    followup_count: int,
) -> bool:
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
