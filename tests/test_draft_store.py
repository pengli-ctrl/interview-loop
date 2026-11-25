"""测试模块，覆盖草稿存储相关行为和回归场景。"""
import json
import os
import time
from datetime import datetime, timedelta, timezone

from interview_loop.storage.draft_store import (
    cleanup_expired_drafts,
    delete_interview_draft,
    draft_ttl_days,
    latest_interview_draft,
    load_interview_draft,
    save_interview_draft,
)


def _answered(session_id: str) -> dict:
    """构造包含一轮问答的草稿。

    Args:
        session_id: `session_id` 输入参数，类型为 str。

    Returns:
        函数处理结果，类型为 dict。

    """
    return {
        "session_id": session_id,
        "messages": [
            {"role": "interviewer", "content": "question"},
            {"role": "candidate", "content": "answer"},
        ],
        "retention_policy": "standard",
    }


def test_draft_roundtrip_and_delete(tmp_path):
    """验证草稿往返和删除。

    Args:
        tmp_path: `tmp_path` 输入参数，类型为 未标注。

    """
    data = _answered("session_1")
    path = save_interview_draft(tmp_path, data)
    assert path.exists()
    loaded = load_interview_draft(tmp_path, "session_1")
    assert loaded["session_id"] == data["session_id"]
    assert loaded["messages"] == data["messages"]
    assert loaded["draft_expires_at"]
    assert latest_interview_draft(tmp_path)["session_id"] == "session_1"
    delete_interview_draft(tmp_path, "session_1")
    assert load_interview_draft(tmp_path, "session_1") is None


def test_latest_draft_skips_corrupt_and_zero_answer_files(tmp_path):
    """验证最近草稿跳过损坏和零回答文件。

    Args:
        tmp_path: `tmp_path` 输入参数，类型为 未标注。

    """
    save_interview_draft(tmp_path, _answered("session_good"))
    save_interview_draft(tmp_path, {"session_id": "session_zero", "messages": []})
    corrupt = tmp_path / "drafts" / "session_bad.json"
    corrupt.write_text("{not json", encoding="utf-8")
    assert latest_interview_draft(tmp_path)["session_id"] == "session_good"


def test_expired_draft_is_removed(tmp_path):
    """验证过期草稿判断移除。

    Args:
        tmp_path: `tmp_path` 输入参数，类型为 未标注。

    """
    data = _answered("session_expired")
    path = save_interview_draft(tmp_path, data)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["draft_expires_at"] = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert cleanup_expired_drafts(tmp_path) == 1
    assert not path.exists()


def test_draft_ttl_respects_retention_cap(tmp_path):
    """验证草稿TTL遵守保留上限。

    Args:
        tmp_path: `tmp_path` 输入参数，类型为 未标注。

    """
    assert draft_ttl_days("ephemeral") == 1
    assert draft_ttl_days("standard") == 7
    assert draft_ttl_days("extended") == 7


def test_draft_requires_safe_session_id(tmp_path):
    """验证草稿需要安全会话ID。

    Args:
        tmp_path: `tmp_path` 输入参数，类型为 未标注。

    Raises:
        AssertionError: 当输入、状态或外部依赖不满足要求时抛出 AssertionError。

    """
    try:
        save_interview_draft(tmp_path, {"session_id": "***"})
    except ValueError:
        pass
    else:
        raise AssertionError("unsafe session id should be rejected")


def test_legacy_draft_without_expiry_uses_file_mtime(tmp_path):
    """验证旧版草稿缺少到期时间时按文件 mtime 计算。

    Args:
        tmp_path: `tmp_path` 输入参数，类型为 未标注。

    """
    legacy = tmp_path / "drafts" / "legacy.json"
    legacy.parent.mkdir(parents=True)
    legacy.write_text(json.dumps({"session_id": "legacy", "messages": []}), encoding="utf-8")
    old_timestamp = time.time() - 8 * 24 * 60 * 60
    os.utime(legacy, (old_timestamp, old_timestamp))
    assert cleanup_expired_drafts(tmp_path) == 1
    assert not legacy.exists()
