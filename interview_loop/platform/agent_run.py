from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4


class RunStatus(Enum):
    CREATED = "created"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class AgentEvent:
    event_type: str
    node: str
    payload: dict = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now)
    duration_ms: int | None = None


@dataclass
class AgentRun:
    tenant_id: str = "default"
    user_id: str = "anonymous"
    workflow_version: str = "v1"
    run_id: str = field(default_factory=lambda: str(uuid4()))
    status: RunStatus = RunStatus.CREATED
    current_node: str = ""
    events: list[AgentEvent] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)

    def start(self, node: str = "interview.start") -> None:
        self.status = RunStatus.RUNNING
        self.current_node = node
        self.record_event("run.started", node)

    def record_event(
        self,
        event_type: str,
        node: str,
        payload: dict | None = None,
        duration_ms: int | None = None,
    ) -> None:
        self.current_node = node
        self.events.append(
            AgentEvent(
                event_type=event_type,
                node=node,
                payload=payload or {},
                duration_ms=duration_ms,
            )
        )
        self.updated_at = utc_now()

    def complete(self, node: str = "interview.complete") -> None:
        self.status = RunStatus.COMPLETED
        self.record_event("run.completed", node)

    def fail(self, error: str, node: str = "interview.error") -> None:
        self.status = RunStatus.FAILED
        self.record_event("run.failed", node, {"error": error})

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "tenant_id": self.tenant_id,
            "user_id": self.user_id,
            "workflow_version": self.workflow_version,
            "status": self.status.value,
            "current_node": self.current_node,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "events": [event.__dict__ for event in self.events],
        }
