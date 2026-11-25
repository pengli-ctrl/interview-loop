"""测试模块，覆盖 SQLite 仓库相关行为和回归场景。"""
import pytest

from interview_loop.platform.agent_run import AgentRun
from interview_loop.platform.run_repository import (
    AgentRunNotFoundError,
    SQLiteAgentRunRepository,
)


def test_sqlite_repository_persists_run_and_events(tmp_path):
    """验证SQLite仓库持久化运行和事件。

    Args:
        tmp_path: `tmp_path` 输入参数，类型为 未标注。

    """
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
    """验证SQLite仓库过滤由租户。

    Args:
        tmp_path: `tmp_path` 输入参数，类型为 未标注。

    """
    repository = SQLiteAgentRunRepository(tmp_path / "runs.db")
    repository.create(AgentRun(tenant_id="tenant-a"))
    repository.create(AgentRun(tenant_id="tenant-b"))
    assert len(repository.list("tenant-a")) == 1
    assert len(repository.list("tenant-b")) == 1


def test_sqlite_repository_delete_and_purge_expired(tmp_path):
    """验证SQLite仓库删除和清理过期。

    Args:
        tmp_path: `tmp_path` 输入参数，类型为 未标注。

    """
    repository = SQLiteAgentRunRepository(tmp_path / "runs.db")
    expired = repository.create(AgentRun(tenant_id="t1", consent_granted=True))
    expired.retention_expires_at = "2000-01-01T00:00:00+00:00"
    repository.save(expired)
    active = repository.create(AgentRun(tenant_id="t1", consent_granted=True))

    assert repository.purge_expired() == 1
    with pytest.raises(AgentRunNotFoundError):
        repository.get(expired.run_id)

    repository.delete(active.run_id)
    with pytest.raises(AgentRunNotFoundError):
        repository.get(active.run_id)
