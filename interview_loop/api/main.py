import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from interview_loop.config import BASE_DIR
from interview_loop.platform.agent_run import AgentRun
from interview_loop.platform.builtin_tools import build_default_tool_registry
from interview_loop.platform.run_repository import (
    AgentRunNotFoundError,
    AgentRunRepository,
    SQLiteAgentRunRepository,
)


class CreateRunRequest(BaseModel):
    tenant_id: str = "default"
    user_id: str = "anonymous"
    workflow_version: str = "v1"
    metadata: dict = Field(default_factory=dict)


class AppendEventRequest(BaseModel):
    event_type: str
    node: str
    payload: dict = Field(default_factory=dict)
    duration_ms: int | None = None


def create_app(
    repository: AgentRunRepository | None = None,
    tool_registry=None,
) -> FastAPI:
    app = FastAPI(
        title="InterviewLoop Agent API",
        version="0.1.0",
        description="Vertical agent-platform slice for interview run orchestration.",
    )
    db_path = Path(os.getenv("INTERVIEWLOOP_DB_PATH", BASE_DIR / "interview_loop.db"))
    app.state.repository = repository or SQLiteAgentRunRepository(db_path)
    app.state.tool_registry = tool_registry or build_default_tool_registry()

    def repo(request: Request) -> AgentRunRepository:
        return request.app.state.repository

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "service": "interview-loop-api", "version": app.version}

    @app.get("/v1/tools")
    def list_tools(request: Request) -> dict:
        return {
            "tools": [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "version": tool.version,
                    "timeout_seconds": tool.timeout_seconds,
                    "required_permission": tool.required_permission,
                }
                for tool in request.app.state.tool_registry.list_tools()
            ]
        }

    @app.post("/v1/agent-runs", status_code=201)
    def create_run(request: Request, body: CreateRunRequest) -> dict:
        run = AgentRun(
            tenant_id=body.tenant_id,
            user_id=body.user_id,
            workflow_version=body.workflow_version,
            metadata=body.metadata,
        )
        return repo(request).create(run).to_dict()

    @app.get("/v1/agent-runs")
    def list_runs(request: Request, tenant_id: str | None = None) -> dict:
        return {"runs": [run.to_dict() for run in repo(request).list(tenant_id)]}

    @app.get("/v1/agent-runs/{run_id}")
    def get_run(request: Request, run_id: str) -> dict:
        try:
            return repo(request).get(run_id).to_dict()
        except AgentRunNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Agent run not found") from exc

    @app.post("/v1/agent-runs/{run_id}/start")
    def start_run(request: Request, run_id: str) -> dict:
        try:
            run = repo(request).get(run_id)
        except AgentRunNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Agent run not found") from exc
        run.start()
        return repo(request).save(run).to_dict()

    @app.post("/v1/agent-runs/{run_id}/events")
    def append_event(request: Request, run_id: str, body: AppendEventRequest) -> dict:
        try:
            run = repo(request).get(run_id)
        except AgentRunNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Agent run not found") from exc
        run.record_event(body.event_type, body.node, body.payload, body.duration_ms)
        return repo(request).save(run).to_dict()

    return app


app = create_app()
