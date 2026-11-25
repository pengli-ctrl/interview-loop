import asyncio
import json
import os
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from interview_loop.api.security import Principal, get_principal
from interview_loop.platform.agent_run import AgentRun, RunStatus
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


class FailRunRequest(BaseModel):
    error: str
    node: str = "interview.error"


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

    @app.post("/v1/agent-runs/{run_id}/complete")
    def complete_run(
        request: Request,
        run_id: str,
        current: Principal = Depends(principal),
    ) -> dict:
        run = owned_run(request, run_id, current)
        run.complete()
        return repo(request).save(run).to_dict()

    @app.post("/v1/agent-runs/{run_id}/fail")
    def fail_run(
        request: Request,
        run_id: str,
        body: FailRunRequest,
        current: Principal = Depends(principal),
    ) -> dict:
        run = owned_run(request, run_id, current)
        run.fail(body.error, body.node)
        return repo(request).save(run).to_dict()

    @app.get("/v1/agent-runs/{run_id}/events/stream")
    async def stream_events(
        request: Request,
        run_id: str,
        current: Principal = Depends(principal),
    ) -> StreamingResponse:
        owned_run(request, run_id, current)

        async def event_generator():
            last_index = 0
            keepalive_ticks = 0
            while True:
                run = repo(request).get(run_id)
                if run.tenant_id != current.tenant_id:
                    return
                for event in run.events[last_index:]:
                    payload = {
                        "event_type": event.event_type,
                        "node": event.node,
                        "payload": event.payload,
                        "created_at": event.created_at,
                        "duration_ms": event.duration_ms,
                    }
                    yield (
                        f"id: {last_index}\n"
                        f"event: {event.event_type}\n"
                        f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                    )
                    last_index += 1
                if run.status in {RunStatus.COMPLETED, RunStatus.FAILED}:
                    return
                keepalive_ticks += 1
                if keepalive_ticks % 10 == 0:
                    yield ": keep-alive\n\n"
                await asyncio.sleep(1)

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return app


app = create_app()
