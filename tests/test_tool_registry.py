import time

import pytest

from interview_loop.platform.tool_registry import (
    ToolExecutionError,
    ToolIdempotencyConflictError,
    ToolNotFoundError,
    ToolPermissionError,
    ToolRegistry,
    ToolSchemaError,
    ToolSpec,
    ToolTimeoutError,
)


def test_register_and_execute_tool():
    registry = ToolRegistry()
    registry.register(ToolSpec("add", "add numbers", lambda a, b: a + b))
    result = registry.execute("add", a=2, b=3)
    assert result.output == 5
    assert result.tool_name == "add"
    assert result.attempts == 1
    assert not result.cached


def test_duplicate_tool_rejected():
    registry = ToolRegistry()
    registry.register(ToolSpec("echo", "echo", lambda value: value))
    with pytest.raises(ValueError):
        registry.register(ToolSpec("echo", "echo", lambda value: value))


def test_missing_tool_raises():
    registry = ToolRegistry()
    with pytest.raises(ToolNotFoundError):
        registry.get("missing")


def test_tool_error_wrapped():
    registry = ToolRegistry()
    registry.register(ToolSpec("fail", "always fail", lambda: 1 / 0))
    with pytest.raises(ToolExecutionError):
        registry.execute("fail")


def test_tool_permission_required():
    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            "export",
            "export",
            lambda: "ok",
            required_permission="record:write",
        )
    )
    with pytest.raises(ToolPermissionError):
        registry.execute("export")
    assert registry.execute("export", permissions={"record:write"}).output == "ok"


def test_tool_timeout_is_enforced():
    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            "slow",
            "sleep past the timeout",
            lambda: time.sleep(0.2),
            timeout_seconds=0.03,
            idempotent=True,
        )
    )
    started = time.perf_counter()
    with pytest.raises(ToolTimeoutError):
        registry.execute("slow")
    assert time.perf_counter() - started < 0.15


def test_retry_requires_idempotent_tool():
    registry = ToolRegistry()
    with pytest.raises(ValueError, match="idempotent"):
        registry.register(
            ToolSpec(
                "unsafe-retry",
                "unsafe",
                lambda: "ok",
                max_retries=1,
            )
        )


def test_idempotent_tool_retries_transient_error():
    calls = []

    def flaky():
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("temporary")
        return "recovered"

    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            "flaky",
            "temporary failure",
            flaky,
            max_retries=1,
            idempotent=True,
        )
    )
    result = registry.execute("flaky")
    assert result.output == "recovered"
    assert result.attempts == 2
    assert len(calls) == 2


def test_idempotency_key_reuses_successful_result():
    calls = []

    def work(value):
        calls.append(value)
        return value

    registry = ToolRegistry()
    registry.register(
        ToolSpec("work", "idempotent work", work, idempotent=True)
    )
    first = registry.execute(
        "work",
        idempotency_key="request-1",
        tenant_id="tenant-a",
        value=7,
    )
    second = registry.execute(
        "work",
        idempotency_key="request-1",
        tenant_id="tenant-a",
        value=7,
    )
    assert first.output == second.output == 7
    assert not first.cached
    assert second.cached
    assert calls == [7]


def test_idempotency_key_rejects_different_arguments():
    calls = []
    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            "work",
            "idempotent work",
            lambda value: calls.append(value) or value,
            idempotent=True,
        )
    )
    registry.execute(
        "work",
        idempotency_key="request-2",
        tenant_id="tenant-a",
        value=1,
    )
    with pytest.raises(ToolIdempotencyConflictError):
        registry.execute(
            "work",
            idempotency_key="request-2",
            tenant_id="tenant-a",
            value=2,
        )
    assert calls == [1]


def test_audit_events_include_tool_and_tenant_context():
    events = []
    registry = ToolRegistry()
    registry.register(ToolSpec("echo", "echo", lambda value: value))

    result = registry.execute(
        "echo",
        tenant_id="tenant-a",
        user_id="user-a",
        run_id="run-a",
        audit_sink=events.append,
        value="hello",
    )

    assert result.output == "hello"
    assert [event.event_type for event in events] == [
        "tool.started",
        "tool.completed",
    ]
    assert events[-1].tenant_id == "tenant-a"
    assert events[-1].run_id == "run-a"
    assert events[-1].input_digest


def test_input_schema_rejects_before_handler_execution():
    calls = []
    events = []
    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            "strict",
            "strict input",
            lambda value: calls.append(value) or value,
            input_schema={
                "type": "object",
                "required": ["value"],
                "properties": {"value": {"type": "integer"}},
                "additionalProperties": False,
            },
        )
    )
    with pytest.raises(ToolSchemaError, match="input schema"):
        registry.execute("strict", audit_sink=events.append, value="wrong")
    assert calls == []
    assert events[-1].event_type == "tool.schema_rejected"


def test_output_schema_failure_is_audited():
    events = []
    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            "strict-output",
            "strict output",
            lambda: "not-an-integer",
            output_schema={"type": "integer"},
        )
    )
    with pytest.raises(ToolSchemaError, match="output schema"):
        registry.execute("strict-output", audit_sink=events.append)
    assert events[-1].status == "schema_failed"
