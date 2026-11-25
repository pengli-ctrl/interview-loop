from fastapi.testclient import TestClient

from interview_loop.api.main import create_app
from interview_loop.platform.run_repository import InMemoryAgentRunRepository

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
