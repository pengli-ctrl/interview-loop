"""隐私模块，负责 PII 脱敏、保留到期和数据处理辅助逻辑。"""
import re
from datetime import datetime, timedelta, timezone
from typing import Any

RETENTION_POLICY_DAYS = {
    "ephemeral": 1,
    "standard": 30,
    "extended": 365,
}

_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_PHONE_RE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
_ID_CARD_RE = re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)")


def redact_pii(text: str) -> str:
    """对文本中的 PII 做脱敏。

    Args:
        text: `text` 输入参数，类型为 str。

    Returns:
        函数处理结果，类型为 str。

    """
    value = _EMAIL_RE.sub("[EMAIL]", str(text))
    value = _ID_CARD_RE.sub("[ID_CARD]", value)
    value = _PHONE_RE.sub("[PHONE]", value)
    return value


def redact_value(value: Any) -> Any:
    """递归脱敏嵌套数据中的 PII。

    Args:
        value: `value` 输入参数，类型为 Any。

    Returns:
        函数处理结果，类型为 Any。

    """
    if isinstance(value, str):
        return redact_pii(value)
    if isinstance(value, dict):
        return {key: redact_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_value(item) for item in value)
    return value


def sanitize_for_analytics(data: dict) -> dict:
    """清洗分析负载，移除音频等敏感字段。

    Args:
        data: `data` 输入参数，类型为 dict。

    Returns:
        函数处理结果，类型为 dict。

    """
    sanitized = redact_value(data)
    for message in sanitized.get("messages", []):
        if isinstance(message, dict):
            message.pop("audio", None)
    return sanitized


def normalize_retention_policy(policy: str | None) -> str:
    """规范化保留策略名称。

    Args:
        policy: `policy` 输入参数，类型为 str | None。

    Returns:
        函数处理结果，类型为 str。

    Raises:
        ValueError: 当输入、状态或外部依赖不满足要求时抛出 ValueError。

    """
    normalized = (policy or "standard").strip().lower()
    if normalized not in RETENTION_POLICY_DAYS:
        allowed = ", ".join(sorted(RETENTION_POLICY_DAYS))
        raise ValueError(f"Unsupported retention policy: {policy}; allowed: {allowed}")
    return normalized


def retention_expires_at(policy: str | None, *, now: datetime | None = None) -> str:
    """计算数据保留到期时间。

    Args:
        policy: `policy` 输入参数，类型为 str | None。
        now: `now` 关键字参数，类型为 datetime | None。

    Returns:
        函数处理结果，类型为 str。

    """
    normalized = normalize_retention_policy(policy)
    current = now or datetime.now(timezone.utc)
    expires = current + timedelta(days=RETENTION_POLICY_DAYS[normalized])
    return expires.isoformat()
