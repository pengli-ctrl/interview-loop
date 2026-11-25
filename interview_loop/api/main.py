from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from interview_loop.platform.agent_run import AgentRun
from interview_loop.platform.builtin_tools import build_default_tool_registry
from interview_loop.platform.run_repository import (
    AgentRunNotFoundError,
    InMemoryAgentRunRepository,
)

app = FastAPI(
    title="InterviewLoop Agent API",
    version="0.1.0",
    description="Vertical agent-platform slice for interview run orchestration.",
)
repository = InMemoryAgentRunRepository()
tool_registry = build_default_tool_registry()


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


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "interview-loop-api", "version": app.version}


@app.get("/v1/tools")
def list_tools() -> dict:
    return {
        "tools": [
            {
                "name": tool.name,
                "description": tool.description,
                "version": tool.version,
                "timeout_seconds": tool.timeout_seconds,
                "required_permission": tool.required_permission,
            }
            for tool in tool_registry.list_tools()
        ]
    }


@app.post("/v1/agent-runs", status_code=201)
def create_run(request: CreateRunRequest) -> dict:
    run = AgentRun(
        tenant_id=request.tenant_id,
        user_id=request.user_id,
        workflow_version=request.workflow_version,
        metadata=request.metadata,
    )
    repository.create(run)
    return run.to_dict()


@app.get("/v1/agent-runs/{run_id}")
def get_run(run_id: str) -> dict:
    try:
        return repository.get(run_id).to_dict()
    except AgentRunNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Agent run not found") from exc


@app.post("/v1/agent-runs/{run_id}/start")
def start_run(run_id: str) -> dict:
    try:
        run = repository.get(run_id)
    except AgentRunNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Agent run not found") from exc
    run.start()
    repository.save(run)
    return run.to_dict()


@app.post("/v1/agent-runs/{run_id}/events")
def append_event(run_id: str, request: AppendEventRequest) -> dict:
    try:
        run = repository.get(run_id)
    except AgentRunNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Agent run not found") from exc
    run.record_event(request.event_type, request.node, request.payload, request.duration_ms)
    repository.save(run)
    return run.to_dict()
