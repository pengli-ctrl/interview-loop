from interview_loop.platform.agent_run import AgentRun
from interview_loop.platform.run_repository import SQLiteAgentRunRepository


def test_sqlite_repository_persists_run_and_events(tmp_path):
    db_path = tmp_path / "runs.db"
    repository = SQLiteAgentRunRepository(db_path)
    run = repository.create(AgentRun(tenant_id="t1", user_id="u1", metadata={"mode": "technical"}))
    run.start()
    run.record_event("answer.received", "interview.answer", {"answer_length": 20})
    repository.save(run)

    reopened = SQLiteAgentRunRepository(db_path)
    loaded = reopened.get(run.run_id)
    assert loaded.tenant_id == "t1"
    assert loaded.status.value == "running"
    assert [event.event_type for event in loaded.events] == [
        "run.started",
        "answer.received",
    ]


def test_sqlite_repository_filters_by_tenant(tmp_path):
    repository = SQLiteAgentRunRepository(tmp_path / "runs.db")
    repository.create(AgentRun(tenant_id="tenant-a"))
    repository.create(AgentRun(tenant_id="tenant-b"))
    assert len(repository.list("tenant-a")) == 1
    assert len(repository.list("tenant-b")) == 1
