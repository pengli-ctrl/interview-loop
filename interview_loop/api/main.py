import os
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from interview_loop.api.security import Principal, get_principal
from interview_loop.platform.agent_run import AgentRun
from interview_loop.platform.builtin_tools import build_default_tool_registry
from interview_loop.platform.run_repository import (
    AgentRunNotFoundError,
    AgentRunRepository,
    SQLiteAgentRunRepository,
)

BASE_DIR = Path(__file__).resolve().parents[2]


class CreateRunRequest(BaseModel):
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
    api_key: str | None = None,
) -> FastAPI:
    app = FastAPI(
        title="InterviewLoop Agent API",
        version="0.1.0",
        description="Vertical agent-platform slice for interview run orchestration.",
    )
    db_path = Path(os.getenv("INTERVIEWLOOP_DB_PATH", BASE_DIR / "interview_loop.db"))
    app.state.repository = repository or SQLiteAgentRunRepository(db_path)
    app.state.tool_registry = tool_registry or build_default_tool_registry()
    configured_api_key = (
        api_key if api_key is not None else os.getenv("INTERVIEWLOOP_API_KEY", "")
    )

    def repo(request: Request) -> AgentRunRepository:
        return request.app.state.repository

    def principal(request: Request) -> Principal:
        return get_principal(request, configured_api_key)

    def owned_run(request: Request, run_id: str, current: Principal) -> AgentRun:
        try:
            run = repo(request).get(run_id)
        except AgentRunNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Agent run not found") from exc
        if run.tenant_id != current.tenant_id:
            raise HTTPException(status_code=404, detail="Agent run not found")
        return run

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "service": "interview-loop-api", "version": app.version}

    @app.get("/v1/me")
    def me(current: Principal = Depends(principal)) -> dict:
        return {
            "tenant_id": current.tenant_id,
            "user_id": current.user_id,
            "permissions": sorted(current.permissions),
        }

    @app.get("/v1/tools")
    def list_tools(request: Request, current: Principal = Depends(principal)) -> dict:
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
    def create_run(
        request: Request,
        body: CreateRunRequest,
        current: Principal = Depends(principal),
    ) -> dict:
        run = AgentRun(
            tenant_id=current.tenant_id,
            user_id=current.user_id,
            workflow_version=body.workflow_version,
            metadata=body.metadata,
        )
        return repo(request).create(run).to_dict()

    @app.get("/v1/agent-runs")
    def list_runs(
        request: Request,
        current: Principal = Depends(principal),
    ) -> dict:
        return {
            "runs": [run.to_dict() for run in repo(request).list(current.tenant_id)]
        }

    @app.get("/v1/agent-runs/{run_id}")
    def get_run(
        request: Request,
        run_id: str,
        current: Principal = Depends(principal),
    ) -> dict:
        return owned_run(request, run_id, current).to_dict()

    @app.post("/v1/agent-runs/{run_id}/start")
    def start_run(
        request: Request,
        run_id: str,
        current: Principal = Depends(principal),
    ) -> dict:
        run = owned_run(request, run_id, current)
        run.start()
        return repo(request).save(run).to_dict()

    @app.post("/v1/agent-runs/{run_id}/events")
    def append_event(
        request: Request,
        run_id: str,
        body: AppendEventRequest,
        current: Principal = Depends(principal),
    ) -> dict:
        run = owned_run(request, run_id, current)
        run.record_event(body.event_type, body.node, body.payload, body.duration_ms)
        return repo(request).save(run).to_dict()

    return app


app = create_app()
