from datetime import datetime, timezone

import pytest

from interview_loop.platform.privacy import (
    normalize_retention_policy,
    redact_pii,
    redact_value,
    retention_expires_at,
    sanitize_for_analytics,
)
from interview_loop.storage.tenant_paths import (
    safe_tenant_segment,
    tenant_scoped_dir,
)


def test_redact_pii_removes_common_identifiers():
    text = "联系 alice@example.com 或 13800138000，身份证 11010519491231002X"
    redacted = redact_pii(text)
    assert "alice@example.com" not in redacted
    assert "13800138000" not in redacted
    assert "11010519491231002X" not in redacted
    assert "[EMAIL]" in redacted
    assert "[PHONE]" in redacted
    assert "[ID_CARD]" in redacted


def test_redact_value_handles_nested_structures():
    value = {"messages": [{"content": "mail me@example.com"}]}
    redacted = redact_value(value)
    assert redacted["messages"][0]["content"] == "mail [EMAIL]"


def test_sanitize_for_analytics_removes_audio():
    data = {"messages": [{"content": "call 13800138000", "audio": b"raw"}]}
    sanitized = sanitize_for_analytics(data)
    assert sanitized["messages"][0]["content"] == "call [PHONE]"
    assert "audio" not in sanitized["messages"][0]


def test_retention_policy_and_expiry():
    assert normalize_retention_policy("STANDARD") == "standard"
    with pytest.raises(ValueError):
        normalize_retention_policy("forever")
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert retention_expires_at("ephemeral", now=now).startswith("2026-01-02")


def test_tenant_storage_paths_are_sanitized(tmp_path):
    assert safe_tenant_segment("../tenant A") == "tenant_A"
    assert tenant_scoped_dir(tmp_path, "local") == tmp_path
    assert tenant_scoped_dir(tmp_path, "tenant A") == tmp_path / "tenants" / "tenant_A"
