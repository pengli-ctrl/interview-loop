"""面试复盘模块，负责复盘提示词、标签解析和数字分数清洗。"""
import json
import re

_SCORE_LINE = re.compile(
    r"(?im)^\s*(?:[-*]\s*)?(?:评分|打分|总评分|综合得分|总分).*$"
)
_SCORE_VALUE = re.compile(r"(?<!\d)\d+(?:\.\d+)?\s*/\s*10")


def strip_numeric_scores(text: str) -> str:
    """移除复盘文本中的数字评分声明。

    Args:
        text: `text` 输入参数，类型为 str。

    Returns:
        函数处理结果，类型为 str。

    """
    lines = []
    for line in str(text or "").splitlines():
        if _SCORE_LINE.match(line):
            continue
        cleaned = _SCORE_VALUE.sub("", line).strip()
        if cleaned:
            lines.append(cleaned)
    return "\n".join(lines).strip()


def build_review_prompt(
    mode: str,
    style: str,
    valid_tags: list[str],
    messages: list[dict],
) -> str:
    """构建只输出定性评价的复盘提示词。

    Args:
        mode: `mode` 输入参数，类型为 str。
        style: `style` 输入参数，类型为 str。
        valid_tags: `valid_tags` 输入参数，类型为 list[str]。
        messages: `messages` 输入参数，类型为 list[dict]。

    Returns:
        函数处理结果，类型为 str。

    """
    return f"""你是面试评审，轮次：{mode}，风格：{style}。
输出固定结构：
1. 总评（只写文字评价，不输出任何数字分数）
2. ✅ 优点
3. ❌ 不足（附带标签，标签只能从{valid_tags}）
4. 📝 口述优化版本
5. 📚 知识点补充
6. 💡 练习建议
对话记录：{json.dumps(messages, ensure_ascii=False)}"""


def build_tag_prompt(review_text: str, valid_tags: list[str]) -> str:
    """构建薄弱标签提取提示词。

    Args:
        review_text: `review_text` 输入参数，类型为 str。
        valid_tags: `valid_tags` 输入参数，类型为 list[str]。

    Returns:
        函数处理结果，类型为 str。

    """
    return f"""从下面复盘文本提取标签，只输出 JSON 数组，例如 ["Temporal", "落地细节"]。
标签只能从列表选择：{",".join(valid_tags)}
文本：{review_text}"""


def parse_tags(raw: str, valid_tags: list[str]) -> list[str]:
    """从模型输出中解析合法标签。

    Args:
        raw: `raw` 输入参数，类型为 str。
        valid_tags: `valid_tags` 输入参数，类型为 list[str]。

    Returns:
        函数处理结果，类型为 list[str]。

    """
    start = raw.find("[")
    end = raw.rfind("]")
    if start == -1 or end < start:
        return []
    try:
        parsed = json.loads(raw[start : end + 1])
    except (TypeError, json.JSONDecodeError):
        return []
    if not isinstance(parsed, list):
        return []
    return [tag for tag in parsed if tag in valid_tags]
