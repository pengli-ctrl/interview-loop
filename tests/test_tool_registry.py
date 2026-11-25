import pytest

from interview_loop.platform.tool_registry import (
    ToolExecutionError,
    ToolNotFoundError,
    ToolPermissionError,
    ToolRegistry,
    ToolSpec,
)


def test_register_and_execute_tool():
    registry = ToolRegistry()
    registry.register(ToolSpec("add", "add numbers", lambda a, b: a + b))
    result = registry.execute("add", a=2, b=3)
    assert result.output == 5
    assert result.tool_name == "add"


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
    registry.register(ToolSpec("export", "export", lambda: "ok", required_permission="record:write"))
    with pytest.raises(ToolPermissionError):
        registry.execute("export")
    assert registry.execute("export", permissions={"record:write"}).output == "ok"
