"""测试模块，覆盖工具注册表相关行为和回归场景。"""
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
    """验证注册和执行工具。"""
    registry = ToolRegistry()
    registry.register(ToolSpec("add", "add numbers", lambda a, b: a + b))
    result = registry.execute("add", a=2, b=3)
    assert result.output == 5
    assert result.tool_name == "add"
    assert result.attempts == 1
    assert not result.cached


def test_duplicate_tool_rejected():
    """验证重复工具被拒绝。"""
    registry = ToolRegistry()
    registry.register(ToolSpec("echo", "echo", lambda value: value))
    with pytest.raises(ValueError):
        registry.register(ToolSpec("echo", "echo", lambda value: value))


def test_missing_tool_raises():
    """验证缺失工具抛出异常。"""
    registry = ToolRegistry()
    with pytest.raises(ToolNotFoundError):
        registry.get("missing")


def test_tool_error_wrapped():
    """验证工具错误包装。"""
    registry = ToolRegistry()
    registry.register(ToolSpec("fail", "always fail", lambda: 1 / 0))
    with pytest.raises(ToolExecutionError):
        registry.execute("fail")


def test_tool_permission_required():
    """验证工具权限必需。"""
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
    """验证工具超时判断强制执行。"""
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
    """验证重试需要幂等工具。"""
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
    """验证幂等工具重试瞬时错误。

    Raises:
        RuntimeError: 当输入、状态或外部依赖不满足要求时抛出 RuntimeError。

    """
    calls = []

    def flaky():
        """构造按次数失败的工具函数。

        Returns:
            函数处理结果，类型为 未标注。

        Raises:
            RuntimeError: 当输入、状态或外部依赖不满足要求时抛出 RuntimeError。

        """
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
    """验证幂等键复用成功结果。"""
    calls = []

    def work(value):
        """构造测试用工具函数。

        Args:
            value: `value` 输入参数，类型为 未标注。

        Returns:
            函数处理结果，类型为 未标注。

        """
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
    """验证幂等键拒绝不同参数。"""
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
    """验证审计事件包含工具和租户上下文。"""
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
    """验证输入Schema拒绝之前处理器执行。"""
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
    """验证输出 Schema 校验失败会记录审计。"""
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
