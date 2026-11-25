import json

from interview_loop.storage.session_store import build_session_data, save_session_json


def test_build_session_data():
    data = build_session_data(
        session_id="s1", mode="技术一面", interview_type="闯关全真面试", style="温和",
        messages=[{"role": "candidate", "content": "回答"}], feedback="复盘", tags=["RAG"],
        started_at="2026-11-25_10-00-00", completed_at="2026-11-25 10:30:00", duration_seconds=1800,
    )
    assert data["session_id"] == "s1"
    assert data["time"] == "2026-11-25 10-00-00"
    assert data["duration_seconds"] == 1800


def test_save_session_json(tmp_path):
    data = {"session_id": "s1", "mode": "技术一面"}
    path = save_session_json(tmp_path, data)
    assert path.exists()
    assert json.loads(path.read_text(encoding="utf-8"))["mode"] == "技术一面"
