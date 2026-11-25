"""AgentRun 模块，负责运行状态、事件、Trace、保留策略和导出结构。"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4

from interview_loop.platform.privacy import (
    normalize_retention_policy,
    redact_value,
    retention_expires_at,
)


class RunStatus(Enum):
    """AgentRun 状态枚举。"""
    CREATED = "created"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


def utc_now() -> str:
    """返回带时区的当前 UTC 时间。

    Returns:
        函数处理结果，类型为 str。

    """
    return datetime.now(timezone.utc).isoformat()


@dataclass
class AgentEvent:
    """AgentRun 事件数据模型。"""
    event_type: str
    node: str
    payload: dict = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now)
    duration_ms: int | None = None


@dataclass
class AgentRun:
    """Agent 运行实例数据模型。"""
    tenant_id: str = "default"
    user_id: str = "anonymous"
    workflow_version: str = "v1"
    trace_id: str = field(default_factory=lambda: str(uuid4()))
    run_id: str = field(default_factory=lambda: str(uuid4()))
    status: RunStatus = RunStatus.CREATED
    current_node: str = ""
    events: list[AgentEvent] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    retention_policy: str = "standard"
    retention_expires_at: str | None = None
    consent_granted: bool = False
    consent_at: str | None = None
    consent_version: str = "v1"
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        """补齐运行时间和 Trace ID。"""
        self.retention_policy = normalize_retention_policy(self.retention_policy)
        if self.retention_expires_at is None:
            self.retention_expires_at = retention_expires_at(self.retention_policy)
        if self.consent_granted and self.consent_at is None:
            self.consent_at = utc_now()

    def start(self, node: str = "interview.start") -> None:
        """启动运行。

        Args:
            node: `node` 输入参数，类型为 str。

        """
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
        """记录一条运行事件。

        Args:
            event_type: `event_type` 输入参数，类型为 str。
            node: `node` 输入参数，类型为 str。
            payload: `payload` 输入参数，类型为 dict | None。
            duration_ms: `duration_ms` 输入参数，类型为 int | None。

        """
        self.current_node = node
        self.events.append(
            AgentEvent(
                event_type=event_type,
                node=node,
                payload=redact_value(payload or {}),
                duration_ms=duration_ms,
            )
        )
        self.updated_at = utc_now()

    def complete(self, node: str = "interview.complete") -> None:
        """把运行标记为完成。

        Args:
            node: `node` 输入参数，类型为 str。

        """
        self.status = RunStatus.COMPLETED
        self.record_event("run.completed", node)

    def fail(self, error: str, node: str = "interview.error") -> None:
        """把运行标记为失败。

        Args:
            error: `error` 输入参数，类型为 str。
            node: `node` 输入参数，类型为 str。

        """
        self.status = RunStatus.FAILED
        self.record_event("run.failed", node, {"error": error})

    def to_dict(self) -> dict:
        """转换为字典。

        Returns:
            函数处理结果，类型为 dict。

        """
        return {
            "run_id": self.run_id,
            "trace_id": self.trace_id,
            "tenant_id": self.tenant_id,
            "user_id": self.user_id,
            "workflow_version": self.workflow_version,
            "status": self.status.value,
            "current_node": self.current_node,
            "metadata": redact_value(self.metadata),
            "retention_policy": self.retention_policy,
            "retention_expires_at": self.retention_expires_at,
            "consent_granted": self.consent_granted,
            "consent_at": self.consent_at,
            "consent_version": self.consent_version,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "events": [event.__dict__ for event in self.events],
        }
