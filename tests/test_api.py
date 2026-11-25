from fastapi.testclient import TestClient

from interview_loop.api.main import create_app
from interview_loop.platform.run_repository import InMemoryAgentRunRepository

client = TestClient(create_app(repository=InMemoryAgentRunRepository()))


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
    created = client.post(
        "/v1/agent-runs",
        json={"tenant_id": "tenant-a", "user_id": "user-a", "metadata": {"mode": "technical"}},
    )
    assert created.status_code == 201
    run_id = created.json()["run_id"]

    listed = client.get("/v1/agent-runs", params={"tenant_id": "tenant-a"})
    assert listed.status_code == 200
    assert any(run["run_id"] == run_id for run in listed.json()["runs"])

    started = client.post(f"/v1/agent-runs/{run_id}/start")
    assert started.status_code == 200
    assert started.json()["status"] == "running"

    event = client.post(
        f"/v1/agent-runs/{run_id}/events",
        json={"event_type": "answer.received", "node": "interview.answer", "payload": {"length": 42}},
    )
    assert event.status_code == 200
    assert event.json()["events"][-1]["event_type"] == "answer.received"


def test_missing_run_returns_404():
    response = client.get("/v1/agent-runs/not-found")
    assert response.status_code == 404
