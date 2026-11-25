from interview_loop.platform.agent_run import AgentRun, RunStatus


def test_agent_run_lifecycle():
    run = AgentRun(tenant_id="t1", user_id="u1", metadata={"mode": "技术一面"})
    run.start()
    assert run.status is RunStatus.RUNNING
    assert run.events[-1].event_type == "run.started"
    run.record_event("answer.received", "interview.answer", {"answer_length": 30})
    run.complete()
    assert run.status is RunStatus.COMPLETED
    assert run.events[-1].event_type == "run.completed"


def test_agent_run_failure():
    run = AgentRun()
    run.fail("model timeout")
    assert run.status is RunStatus.FAILED
    assert run.events[-1].payload["error"] == "model timeout"


def test_agent_run_serialization():
    run = AgentRun(tenant_id="t1", user_id="u1")
    run.start()
    data = run.to_dict()
    assert data["tenant_id"] == "t1"
    assert data["status"] == "running"
    assert data["events"][0]["event_type"] == "run.started"
