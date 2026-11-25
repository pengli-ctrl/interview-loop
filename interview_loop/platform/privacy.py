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
    value = _EMAIL_RE.sub("[EMAIL]", str(text))
    value = _ID_CARD_RE.sub("[ID_CARD]", value)
    value = _PHONE_RE.sub("[PHONE]", value)
    return value


def redact_value(value: Any) -> Any:
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
    sanitized = redact_value(data)
    for message in sanitized.get("messages", []):
        if isinstance(message, dict):
            message.pop("audio", None)
    return sanitized


def normalize_retention_policy(policy: str | None) -> str:
    normalized = (policy or "standard").strip().lower()
    if normalized not in RETENTION_POLICY_DAYS:
        allowed = ", ".join(sorted(RETENTION_POLICY_DAYS))
        raise ValueError(f"Unsupported retention policy: {policy}; allowed: {allowed}")
    return normalized


def retention_expires_at(policy: str | None, *, now: datetime | None = None) -> str:
    normalized = normalize_retention_policy(policy)
    current = now or datetime.now(timezone.utc)
    expires = current + timedelta(days=RETENTION_POLICY_DAYS[normalized])
    return expires.isoformat()
