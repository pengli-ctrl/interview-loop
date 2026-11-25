import json
import sqlite3
from pathlib import Path
from typing import Protocol

from interview_loop.platform.agent_run import AgentEvent, AgentRun, RunStatus


class AgentRunNotFoundError(LookupError):
    pass


class AgentRunRepository(Protocol):
    def create(self, run: AgentRun) -> AgentRun: ...
    def get(self, run_id: str) -> AgentRun: ...
    def save(self, run: AgentRun) -> AgentRun: ...
    def list(self, tenant_id: str | None = None) -> list[AgentRun]: ...


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
                    tenant_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    workflow_version TEXT NOT NULL,
                    status TEXT NOT NULL,
                    current_node TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
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

    def create(self, run: AgentRun) -> AgentRun:
        return self.save(run)

    def save(self, run: AgentRun) -> AgentRun:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO agent_runs (
                    run_id, tenant_id, user_id, workflow_version, status,
                    current_node, metadata_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    status = excluded.status,
                    current_node = excluded.current_node,
                    metadata_json = excluded.metadata_json,
                    updated_at = excluded.updated_at
                """,
                (
                    run.run_id,
                    run.tenant_id,
                    run.user_id,
                    run.workflow_version,
                    run.status.value,
                    run.current_node,
                    json.dumps(run.metadata, ensure_ascii=False),
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

    @staticmethod
    def _to_run(run_row, event_rows: list) -> AgentRun:
        return AgentRun(
            run_id=run_row["run_id"],
            tenant_id=run_row["tenant_id"],
            user_id=run_row["user_id"],
            workflow_version=run_row["workflow_version"],
            status=RunStatus(run_row["status"]),
            current_node=run_row["current_node"],
            metadata=json.loads(run_row["metadata_json"]),
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
