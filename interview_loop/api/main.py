import asyncio
import base64
import json
import os
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, Field

from interview_loop.api.security import Principal, get_principal
from interview_loop.evaluation.agent_metrics import summarize_agent_runs
from interview_loop.platform.agent_run import AgentRun, RunStatus
from interview_loop.platform.builtin_tools import build_default_tool_registry
from interview_loop.platform.run_repository import (
    AgentRunNotFoundError,
    AgentRunRepository,
    SQLiteAgentRunRepository,
)
from interview_loop.platform.tool_registry import (
    ToolAuditEvent,
    ToolExecutionError,
    ToolIdempotencyConflictError,
    ToolNotFoundError,
    ToolPermissionError,
    ToolSchemaError,
    ToolTimeoutError,
)

BASE_DIR = Path(__file__).resolve().parents[2]


class CreateRunRequest(BaseModel):
    workflow_version: str = "v1"
    metadata: dict = Field(default_factory=dict)
    retention_policy: str = "standard"
    consent_granted: bool = False
    consent_version: str = "v1"


class AppendEventRequest(BaseModel):
    event_type: str
    node: str
    payload: dict = Field(default_factory=dict)
    duration_ms: int | None = None


class FailRunRequest(BaseModel):
    error: str
    node: str = "interview.error"


class ExecuteToolRequest(BaseModel):
    arguments: dict = Field(default_factory=dict)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=200)


def serialize_tool_output(output):
    if isinstance(output, bytes):
        return {
            "type": "bytes",
            "encoding": "base64",
            "data": base64.b64encode(output).decode("ascii"),
        }
    if isinstance(output, Path):
        return str(output)
    return jsonable_encoder(output)


def create_app(
    repository: AgentRunRepository | None = None,
    tool_registry=None,
    api_key: str | None = None,
) -> FastAPI:
    app = FastAPI(
        title="InterviewLoop Agent API",
        version="0.10.0",
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
                    "max_retries": tool.max_retries,
                    "idempotent": tool.idempotent,
                    "idempotency_ttl_seconds": tool.idempotency_ttl_seconds,
                    "input_schema": tool.input_schema,
                    "output_schema": tool.output_schema,
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
        if not body.consent_granted:
            raise HTTPException(
                status_code=422,
                detail="Explicit recording and retention consent is required",
            )
        try:
            run = AgentRun(
                tenant_id=current.tenant_id,
                user_id=current.user_id,
                workflow_version=body.workflow_version,
                metadata=body.metadata,
                retention_policy=body.retention_policy,
                consent_granted=body.consent_granted,
                consent_version=body.consent_version,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return repo(request).create(run).to_dict()

    @app.get("/v1/agent-runs")
    def list_runs(
        request: Request,
        current: Principal = Depends(principal),
    ) -> dict:
        return {
            "runs": [run.to_dict() for run in repo(request).list(current.tenant_id)]
        }

    @app.get("/v1/metrics")
    def metrics(
        request: Request,
        current: Principal = Depends(principal),
    ) -> dict:
        runs = [
            run.to_dict() for run in repo(request).list(current.tenant_id)
        ]
        return summarize_agent_runs(runs)

    @app.get("/v1/agent-runs/{run_id}")
    def get_run(
        request: Request,
        run_id: str,
        current: Principal = Depends(principal),
    ) -> dict:
        return owned_run(request, run_id, current).to_dict()

    @app.get("/v1/agent-runs/{run_id}/export")
    def export_run(
        request: Request,
        run_id: str,
        current: Principal = Depends(principal),
    ) -> JSONResponse:
        run = owned_run(request, run_id, current)
        return JSONResponse(
            content=run.to_dict(),
            headers={
                "Content-Disposition": f'attachment; filename="{run_id}.json"'
            },
        )

    @app.delete("/v1/agent-runs/{run_id}", status_code=204)
    def delete_run(
        request: Request,
        run_id: str,
        current: Principal = Depends(principal),
    ) -> Response:
        run = owned_run(request, run_id, current)
        repo(request).delete(run.run_id)
        return Response(status_code=204)

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

    @app.post("/v1/agent-runs/{run_id}/tools/{tool_name}")
    def execute_tool(
        request: Request,
        run_id: str,
        tool_name: str,
        body: ExecuteToolRequest,
        current: Principal = Depends(principal),
    ) -> dict:
        run = owned_run(request, run_id, current)
        if run.status is not RunStatus.RUNNING:
            raise HTTPException(status_code=409, detail="Agent run is not running")

        reserved = {
            "permissions",
            "idempotency_key",
            "tenant_id",
            "user_id",
            "run_id",
            "audit_sink",
        }
        conflict = reserved.intersection(body.arguments)
        if conflict:
            raise HTTPException(
                status_code=422,
                detail=f"Reserved tool argument(s): {', '.join(sorted(conflict))}",
            )

        def audit(event: ToolAuditEvent) -> None:
            run.record_event(
                event.event_type,
                f"tool.{event.tool_name}",
                event.to_payload(),
                event.duration_ms,
            )

        try:
            result = request.app.state.tool_registry.execute(
                tool_name,
                permissions=current.permissions,
                idempotency_key=body.idempotency_key,
                tenant_id=current.tenant_id,
                user_id=current.user_id,
                run_id=run_id,
                audit_sink=audit,
                **body.arguments,
            )
        except ToolNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Tool not found") from exc
        except ToolPermissionError as exc:
            repo(request).save(run)
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except ToolTimeoutError as exc:
            repo(request).save(run)
            raise HTTPException(status_code=504, detail=str(exc)) from exc
        except ToolIdempotencyConflictError as exc:
            repo(request).save(run)
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ToolSchemaError as exc:
            repo(request).save(run)
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except ToolExecutionError as exc:
            repo(request).save(run)
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        repo(request).save(run)
        return {
            "run_id": run_id,
            "tool_name": result.tool_name,
            "tool_version": result.tool_version,
            "output": serialize_tool_output(result.output),
            "duration_ms": result.duration_ms,
            "attempts": result.attempts,
            "cached": result.cached,
        }

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
