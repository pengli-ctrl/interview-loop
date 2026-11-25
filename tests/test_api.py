import time

from fastapi.testclient import TestClient

from interview_loop.api.main import create_app
from interview_loop.platform.run_repository import InMemoryAgentRunRepository
from interview_loop.platform.tool_registry import ToolRegistry, ToolSpec

app = create_app(repository=InMemoryAgentRunRepository(), api_key=None)
client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_tool_catalog():
    response = client.get("/v1/tools")
    assert response.status_code == 200
    names = {tool["name"] for tool in response.json()["tools"]}
    assert {"resume.decode", "asr.transcribe", "tts.synthesize", "record.export"} <= names


def test_run_lifecycle_and_event_append():
    headers = {"X-Tenant-Id": "tenant-a", "X-User-Id": "user-a"}
    created = client.post(
        "/v1/agent-runs",
        headers=headers,
        json={"metadata": {"mode": "technical"}},
    )
    assert created.status_code == 201
    run_id = created.json()["run_id"]
    assert created.json()["tenant_id"] == "tenant-a"

    listed = client.get("/v1/agent-runs", headers=headers)
    assert listed.status_code == 200
    assert any(run["run_id"] == run_id for run in listed.json()["runs"])

    started = client.post(f"/v1/agent-runs/{run_id}/start", headers=headers)
    assert started.status_code == 200
    assert started.json()["status"] == "running"

    event = client.post(
        f"/v1/agent-runs/{run_id}/events",
        headers=headers,
        json={"event_type": "answer.received", "node": "interview.answer", "payload": {"length": 42}},
    )
    assert event.status_code == 200
    assert event.json()["events"][-1]["event_type"] == "answer.received"


def test_missing_run_returns_404():
    response = client.get("/v1/agent-runs/not-found", headers={"X-Tenant-Id": "tenant-a"})
    assert response.status_code == 404


def test_tenant_isolation():
    created = client.post(
        "/v1/agent-runs",
        headers={"X-Tenant-Id": "tenant-a"},
        json={"metadata": {}},
    )
    run_id = created.json()["run_id"]
    response = client.get(
        f"/v1/agent-runs/{run_id}",
        headers={"X-Tenant-Id": "tenant-b"},
    )
    assert response.status_code == 404


def test_api_key_authentication():
    secured = TestClient(create_app(repository=InMemoryAgentRunRepository(), api_key="secret"))
    assert secured.get("/health").status_code == 200
    assert secured.get("/v1/tools").status_code == 401
    assert secured.get("/v1/tools", headers={"X-API-Key": "secret"}).status_code == 200


def test_complete_run_and_stream_events():
    headers = {"X-Tenant-Id": "tenant-stream"}
    created = client.post("/v1/agent-runs", headers=headers, json={"metadata": {}})
    run_id = created.json()["run_id"]
    client.post(f"/v1/agent-runs/{run_id}/start", headers=headers)
    client.post(
        f"/v1/agent-runs/{run_id}/events",
        headers=headers,
        json={"event_type": "answer.received", "node": "interview.answer", "payload": {}},
    )
    completed = client.post(f"/v1/agent-runs/{run_id}/complete", headers=headers)
    assert completed.json()["status"] == "completed"

    response = client.get(
        f"/v1/agent-runs/{run_id}/events/stream",
        headers=headers,
    )
    assert response.status_code == 200
    assert "event: run.started" in response.text
    assert "event: answer.received" in response.text
    assert "event: run.completed" in response.text


def test_tool_execution_records_audit_and_reuses_idempotency_key():
    headers = {"X-Tenant-Id": "tenant-tools", "X-User-Id": "user-tools"}
    created = client.post("/v1/agent-runs", headers=headers, json={"metadata": {}})
    run_id = created.json()["run_id"]
    client.post(f"/v1/agent-runs/{run_id}/start", headers=headers)
    payload = {
        "arguments": {
            "new_question": "Explain RAG retrieval.",
            "previous_question": "Explain RAG retrieval.",
        },
        "idempotency_key": "tool-cache-1",
    }

    first = client.post(
        f"/v1/agent-runs/{run_id}/tools/question.similarity",
        headers=headers,
        json=payload,
    )
    second = client.post(
        f"/v1/agent-runs/{run_id}/tools/question.similarity",
        headers=headers,
        json=payload,
    )

    assert first.status_code == 200
    assert first.json()["output"] is True
    assert first.json()["cached"] is False
    assert second.status_code == 200
    assert second.json()["cached"] is True

    conflict = client.post(
        f"/v1/agent-runs/{run_id}/tools/question.similarity",
        headers=headers,
        json={
            "arguments": {
                "new_question": "Explain RAG.",
                "previous_question": "Explain caching.",
            },
            "idempotency_key": "tool-cache-1",
        },
    )
    assert conflict.status_code == 409

    run = client.get(f"/v1/agent-runs/{run_id}", headers=headers).json()
    event_types = [event["event_type"] for event in run["events"]]
    assert event_types.count("tool.completed") == 1
    assert "tool.started" in event_types
    assert "tool.cache_hit" in event_types
    assert "tool.idempotency_conflict" in event_types


def test_tool_permission_is_enforced_before_execution():
    headers = {"X-Tenant-Id": "tenant-tool-denied"}
    created = client.post("/v1/agent-runs", headers=headers, json={"metadata": {}})
    run_id = created.json()["run_id"]
    client.post(f"/v1/agent-runs/{run_id}/start", headers=headers)

    response = client.post(
        f"/v1/agent-runs/{run_id}/tools/record.export",
        headers=headers,
        json={"arguments": {}},
    )

    assert response.status_code == 403
    run = client.get(f"/v1/agent-runs/{run_id}", headers=headers).json()
    assert run["events"][-1]["event_type"] == "tool.denied"


def test_tool_timeout_returns_gateway_timeout_and_is_audited():
    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            "slow",
            "slow tool",
            lambda: time.sleep(0.2),
            timeout_seconds=0.02,
            idempotent=True,
        )
    )
    timeout_client = TestClient(
        create_app(
            repository=InMemoryAgentRunRepository(),
            tool_registry=registry,
            api_key=None,
        )
    )
    headers = {"X-Tenant-Id": "tenant-timeout"}
    created = timeout_client.post(
        "/v1/agent-runs",
        headers=headers,
        json={"metadata": {}},
    )
    run_id = created.json()["run_id"]
    timeout_client.post(f"/v1/agent-runs/{run_id}/start", headers=headers)

    response = timeout_client.post(
        f"/v1/agent-runs/{run_id}/tools/slow",
        headers=headers,
        json={"arguments": {}},
    )

    assert response.status_code == 504
    run = timeout_client.get(
        f"/v1/agent-runs/{run_id}",
        headers=headers,
    ).json()
    failed = [event for event in run["events"] if event["event_type"] == "tool.failed"]
    assert failed[-1]["payload"]["status"] == "timeout"
