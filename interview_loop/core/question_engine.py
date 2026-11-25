"""问题生成模块，负责阶段提示词、相似问题修复和兜底追问。"""
from dataclasses import dataclass
from difflib import SequenceMatcher

SIMILARITY_THRESHOLD = 0.82


def questions_too_similar(new_question: str, previous_question: str) -> bool:
    """判断两个问题是否过于相似。

    Args:
        new_question: `new_question` 输入参数，类型为 str。
        previous_question: `previous_question` 输入参数，类型为 str。

    Returns:
        函数处理结果，类型为 bool。

    """
    def normalize(value: str) -> str:
        """去除标点并转为小写。

        Args:
            value: `value` 输入参数，类型为 str。

        Returns:
            函数处理结果，类型为 str。

        """
        return "".join(char.lower() for char in value if char.isalnum())

    left = normalize(new_question)
    right = normalize(previous_question)
    if not left or not right:
        return False
    if left == right or left in right or right in left:
        return True
    return SequenceMatcher(None, left, right).ratio() >= SIMILARITY_THRESHOLD


@dataclass(frozen=True)
class StageQuestionPrompt:
    """阶段问题的系统提示词和当前主题。"""
    system_prompt: str
    current_topic: str


def build_stage_question_prompt(
    *,
    mode: str,
    style: str,
    stage: dict,
    resume_ctx: str,
    weak_stats: dict,
    main_index: int,
    followup_index: int,
    is_followup: bool,
    previous_question: str,
    last_answer: str,
    job_ctx: str = "",
) -> StageQuestionPrompt:
    """构建带阶段约束的出题提示词。

    Args:
        mode: `mode` 关键字参数，类型为 str。
        style: `style` 关键字参数，类型为 str。
        stage: `stage` 关键字参数，类型为 dict。
        resume_ctx: `resume_ctx` 关键字参数，类型为 str。
        weak_stats: `weak_stats` 关键字参数，类型为 dict。
        main_index: `main_index` 关键字参数，类型为 int。
        followup_index: `followup_index` 关键字参数，类型为 int。
        is_followup: `is_followup` 关键字参数，类型为 bool。
        previous_question: `previous_question` 关键字参数，类型为 str。
        last_answer: `last_answer` 关键字参数，类型为 str。
        job_ctx: `job_ctx` 关键字参数，类型为 str。

    Returns:
        函数处理结果，类型为 StageQuestionPrompt。

    """
    question_plan = stage.get("question_plan") or stage.get("pool") or [stage["desc"]]
    main_total = max(1, len(question_plan))
    main_index = min(max(0, main_index), main_total - 1)
    max_followups = max(0, int(stage.get("max_followups", 0)))
    current_topic = question_plan[main_index]
    weak_tags = [
        key for key, _ in sorted(weak_stats.items(), key=lambda item: item[1], reverse=True)
    ]
    question_type = "追问" if is_followup else "主问题"
    system_prompt = f"""你是【{mode}】面试官，风格：{style}。
当前面试阶段：{stage['name']}，考察方向：{stage['desc']}
本阶段主问题计划：{question_plan}
当前主问题：第 {main_index + 1}/{main_total} 个：{current_topic}
本题类型：{question_type}
追问进度：{followup_index}/{max_followups}
岗位匹配上下文：{job_ctx or "无"}
规则：
1. 主问题必须覆盖当前主问题目标，不要提前跳到后续主问题；
2. 如果是追问，必须基于候选人的上一轮回答继续深挖，不能重复上一题；
3. 薄弱标签参考：{weak_tags}
4. 简历上下文：{resume_ctx}
5. 输出只输出题目，不要多余解释；
6. 问题和追问必须严格停留在当前阶段【{stage['name']}】（{stage['desc']}），不得提前进入后续面试阶段；
7. 当前阶段是自我介绍时，只能围绕个人经历、职责范围、技术方向和职业动机，不得追问具体项目架构、技术方案、线上故障或系统设计细节；
8. 除自我介绍阶段外，问题应优先验证岗位匹配上下文中的缺失技能和风险项，但不能偏离当前阶段。
上一题：{previous_question or "无"}
候选人回答：{last_answer or "无"}"""
    return StageQuestionPrompt(system_prompt=system_prompt, current_topic=current_topic)


def build_repair_prompt(system_prompt: str) -> str:
    """构建避免重复问题的修复提示词。

    Args:
        system_prompt: `system_prompt` 输入参数，类型为 str。

    Returns:
        函数处理结果，类型为 str。

    """
    return system_prompt + """
你上一次生成的问题与上一题过于相似。请重新生成一个不同的题目；如果是追问，必须针对候选人回答中的具体内容。"""


def build_similarity_fallback(current_topic: str, last_answer: str) -> str:
    """生成相似问题的兜底追问。

    Args:
        current_topic: `current_topic` 输入参数，类型为 str。
        last_answer: `last_answer` 输入参数，类型为 str。

    Returns:
        函数处理结果，类型为 str。

    """
    answer_excerpt = last_answer.strip().replace("\n", " ")[:60]
    return (
        f"你刚才提到“{answer_excerpt}”，请继续围绕当前主问题“{current_topic}”"
        "说明具体经历、思路和结果，不要提前进入后续阶段。"
    )
