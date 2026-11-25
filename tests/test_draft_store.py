from interview_loop.storage.draft_store import (
    delete_interview_draft,
    latest_interview_draft,
    load_interview_draft,
    save_interview_draft,
)


def test_draft_roundtrip_and_delete(tmp_path):
    data = {"session_id": "session_1", "messages": [{"role": "candidate", "content": "ok"}]}
    path = save_interview_draft(tmp_path, data)
    assert path.exists()
    assert load_interview_draft(tmp_path, "session_1") == data
    assert latest_interview_draft(tmp_path) == data
    delete_interview_draft(tmp_path, "session_1")
    assert load_interview_draft(tmp_path, "session_1") is None


def test_latest_draft_skips_corrupt_files(tmp_path):
    good = {"session_id": "session_good", "messages": []}
    save_interview_draft(tmp_path, good)
    corrupt = tmp_path / "drafts" / "session_bad.json"
    corrupt.write_text("{not json", encoding="utf-8")
    assert latest_interview_draft(tmp_path) == good


def test_draft_requires_safe_session_id(tmp_path):
    try:
        save_interview_draft(tmp_path, {"session_id": "***"})
    except ValueError:
        pass
    else:
        raise AssertionError("unsafe session id should be rejected")
