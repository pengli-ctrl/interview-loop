import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from interview_loop.platform.agent_run import AgentEvent, AgentRun, RunStatus
from interview_loop.platform.privacy import retention_expires_at


class AgentRunNotFoundError(LookupError):
    pass


class AgentRunRepository(Protocol):
    def create(self, run: AgentRun) -> AgentRun: ...
    def get(self, run_id: str) -> AgentRun: ...
    def save(self, run: AgentRun) -> AgentRun: ...
    def list(self, tenant_id: str | None = None) -> list[AgentRun]: ...
    def delete(self, run_id: str) -> None: ...
    def purge_expired(self, at: str | None = None) -> int: ...


class InMemoryAgentRunRepository:
    def __init__(self) -> None:
        self._runs: dict[str, AgentRun] = {}

    def create(self, run: AgentRun) -> AgentRun:
        self._runs[run.run_id] = run
        return run

    def get(self, run_id: str) -> AgentRun:
        try:
            return self._runs[run_id]
        except KeyError as exc:
            raise AgentRunNotFoundError(run_id) from exc

    def save(self, run: AgentRun) -> AgentRun:
        self._runs[run.run_id] = run
        return run

    def list(self, tenant_id: str | None = None) -> list[AgentRun]:
        runs = list(self._runs.values())
        if tenant_id is not None:
            runs = [run for run in runs if run.tenant_id == tenant_id]
        return runs

    def delete(self, run_id: str) -> None:
        try:
            del self._runs[run_id]
        except KeyError as exc:
            raise AgentRunNotFoundError(run_id) from exc

    def purge_expired(self, at: str | None = None) -> int:
        now = datetime.fromisoformat(at) if at else datetime.now(timezone.utc)
        expired = [
            run_id
            for run_id, run in self._runs.items()
            if datetime.fromisoformat(run.retention_expires_at) <= now
        ]
        for run_id in expired:
            self._runs.pop(run_id, None)
        return len(expired)


class SQLiteAgentRunRepository:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS agent_runs (
                    run_id TEXT PRIMARY KEY,
                    trace_id TEXT,
                    tenant_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    workflow_version TEXT NOT NULL,
                    status TEXT NOT NULL,
                    current_node TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    retention_policy TEXT NOT NULL DEFAULT 'standard',
                    retention_expires_at TEXT NOT NULL DEFAULT '',
                    consent_granted INTEGER NOT NULL DEFAULT 0,
                    consent_at TEXT,
                    consent_version TEXT NOT NULL DEFAULT 'v1',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS agent_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    node TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    duration_ms INTEGER,
                    FOREIGN KEY(run_id) REFERENCES agent_runs(run_id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_agent_runs_tenant ON agent_runs(tenant_id);
                CREATE INDEX IF NOT EXISTS idx_agent_events_run ON agent_events(run_id);
                """
            )
            self._ensure_column(connection, "agent_runs", "trace_id", "TEXT")
            self._ensure_column(
                connection,
                "agent_runs",
                "retention_policy",
                "TEXT NOT NULL DEFAULT 'standard'",
            )
            self._ensure_column(
                connection,
                "agent_runs",
                "retention_expires_at",
                "TEXT NOT NULL DEFAULT ''",
            )
            self._ensure_column(
                connection,
                "agent_runs",
                "consent_granted",
                "INTEGER NOT NULL DEFAULT 0",
            )
            self._ensure_column(connection, "agent_runs", "consent_at", "TEXT")
            self._ensure_column(
                connection,
                "agent_runs",
                "consent_version",
                "TEXT NOT NULL DEFAULT 'v1'",
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_agent_runs_expiry "
                "ON agent_runs(retention_expires_at)"
            )

    @staticmethod
    def _ensure_column(
        connection: sqlite3.Connection,
        table: str,
        column: str,
        definition: str,
    ) -> None:
        existing = {
            row["name"] for row in connection.execute(f"PRAGMA table_info({table})")
        }
        if column not in existing:
            connection.execute(
                f"ALTER TABLE {table} ADD COLUMN {column} {definition}"
            )

    def create(self, run: AgentRun) -> AgentRun:
        return self.save(run)

    def save(self, run: AgentRun) -> AgentRun:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO agent_runs (
                    run_id, trace_id, tenant_id, user_id, workflow_version, status,
                    current_node, metadata_json, retention_policy,
                    retention_expires_at, consent_granted, consent_at,
                    consent_version, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    trace_id = excluded.trace_id,
                    status = excluded.status,
                    current_node = excluded.current_node,
                    metadata_json = excluded.metadata_json,
                    retention_policy = excluded.retention_policy,
                    retention_expires_at = excluded.retention_expires_at,
                    consent_granted = excluded.consent_granted,
                    consent_at = excluded.consent_at,
                    consent_version = excluded.consent_version,
                    updated_at = excluded.updated_at
                """,
                (
                    run.run_id,
                    run.trace_id,
                    run.tenant_id,
                    run.user_id,
                    run.workflow_version,
                    run.status.value,
                    run.current_node,
                    json.dumps(run.metadata, ensure_ascii=False),
                    run.retention_policy,
                    run.retention_expires_at,
                    int(run.consent_granted),
                    run.consent_at,
                    run.consent_version,
                    run.created_at,
                    run.updated_at,
                ),
            )
            connection.execute("DELETE FROM agent_events WHERE run_id = ?", (run.run_id,))
            connection.executemany(
                """
                INSERT INTO agent_events (
                    run_id, event_type, node, payload_json, created_at, duration_ms
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        run.run_id,
                        event.event_type,
                        event.node,
                        json.dumps(event.payload, ensure_ascii=False),
                        event.created_at,
                        event.duration_ms,
                    )
                    for event in run.events
                ],
            )
        return run

    def get(self, run_id: str) -> AgentRun:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM agent_runs WHERE run_id = ?", (run_id,)
            ).fetchone()
            if row is None:
                raise AgentRunNotFoundError(run_id)
            event_rows = connection.execute(
                "SELECT * FROM agent_events WHERE run_id = ? ORDER BY id", (run_id,)
            ).fetchall()
        return self._to_run(row, event_rows)

    def list(self, tenant_id: str | None = None) -> list[AgentRun]:
        query = "SELECT * FROM agent_runs"
        params: tuple = ()
        if tenant_id is not None:
            query += " WHERE tenant_id = ?"
            params = (tenant_id,)
        query += " ORDER BY updated_at DESC"
        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [self.get(row["run_id"]) for row in rows]

    def delete(self, run_id: str) -> None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT run_id FROM agent_runs WHERE run_id = ?", (run_id,)
            ).fetchone()
            if row is None:
                raise AgentRunNotFoundError(run_id)
            connection.execute("DELETE FROM agent_events WHERE run_id = ?", (run_id,))
            connection.execute("DELETE FROM agent_runs WHERE run_id = ?", (run_id,))

    def purge_expired(self, at: str | None = None) -> int:
        cutoff = at or datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            expired_ids = [
                row["run_id"]
                for row in connection.execute(
                    """
                    SELECT run_id FROM agent_runs
                    WHERE retention_expires_at != '' AND retention_expires_at <= ?
                    """,
                    (cutoff,),
                ).fetchall()
            ]
            if expired_ids:
                placeholders = ",".join("?" for _ in expired_ids)
                connection.execute(
                    f"DELETE FROM agent_events WHERE run_id IN ({placeholders})",
                    expired_ids,
                )
                connection.execute(
                    f"DELETE FROM agent_runs WHERE run_id IN ({placeholders})",
                    expired_ids,
                )
        return len(expired_ids)

    @staticmethod
    def _to_run(run_row, event_rows: list) -> AgentRun:
        retention_policy = run_row["retention_policy"] or "standard"
        retention_expiry = run_row["retention_expires_at"] or retention_expires_at(
            retention_policy
        )
        return AgentRun(
            run_id=run_row["run_id"],
            trace_id=run_row["trace_id"] or run_row["run_id"],
            tenant_id=run_row["tenant_id"],
            user_id=run_row["user_id"],
            workflow_version=run_row["workflow_version"],
            status=RunStatus(run_row["status"]),
            current_node=run_row["current_node"],
            metadata=json.loads(run_row["metadata_json"]),
            retention_policy=retention_policy,
            retention_expires_at=retention_expiry,
            consent_granted=bool(run_row["consent_granted"]),
            consent_at=run_row["consent_at"],
            consent_version=run_row["consent_version"] or "v1",
            created_at=run_row["created_at"],
            updated_at=run_row["updated_at"],
            events=[
                AgentEvent(
                    event_type=row["event_type"],
                    node=row["node"],
                    payload=json.loads(row["payload_json"]),
                    created_at=row["created_at"],
                    duration_ms=row["duration_ms"],
                )
                for row in event_rows
            ],
        )
