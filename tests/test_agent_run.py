"""测试模块，覆盖 AgentRun 相关行为和回归场景。"""
from interview_loop.platform.agent_run import AgentRun, RunStatus


def test_agent_run_lifecycle():
    """验证Agent运行生命周期。"""
    run = AgentRun(tenant_id="t1", user_id="u1", metadata={"mode": "技术一面"})
    run.start()
    assert run.status is RunStatus.RUNNING
    assert run.events[-1].event_type == "run.started"
    run.record_event("answer.received", "interview.answer", {"answer_length": 30})
    run.complete()
    assert run.status is RunStatus.COMPLETED
    assert run.events[-1].event_type == "run.completed"


def test_agent_run_failure():
    """验证Agent运行失败。"""
    run = AgentRun()
    run.fail("model timeout")
    assert run.status is RunStatus.FAILED
    assert run.events[-1].payload["error"] == "model timeout"


def test_agent_run_serialization():
    """验证Agent运行序列化。"""
    run = AgentRun(tenant_id="t1", user_id="u1")
    run.start()
    data = run.to_dict()
    assert data["tenant_id"] == "t1"
    assert data["status"] == "running"
    assert data["events"][0]["event_type"] == "run.started"


def test_agent_event_payload_is_pii_redacted():
    """验证Agent事件负载判断PII已脱敏。"""
    run = AgentRun()
    run.record_event(
        "candidate.contact",
        "interview.answer",
        {"content": "email me@example.com or call 13800138000"},
    )
    data = run.to_dict()
    content = data["events"][-1]["payload"]["content"]
    assert "me@example.com" not in content
    assert "13800138000" not in content
    assert "[EMAIL]" in content
    assert "[PHONE]" in content


def test_agent_run_records_consent_and_retention():
    """验证 AgentRun 记录同意信息和保留策略。"""
    run = AgentRun(
        tenant_id="tenant-a",
        user_id="user-a",
        retention_policy="ephemeral",
        consent_granted=True,
    )
    data = run.to_dict()
    assert data["tenant_id"] == "tenant-a"
    assert data["trace_id"]
    assert data["retention_policy"] == "ephemeral"
    assert data["retention_expires_at"]
    assert data["consent_granted"] is True
    assert data["consent_at"]
