"""草稿存储模块，负责未完成面试草稿的保存、TTL、清理和删除。"""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from interview_loop.storage.common import atomic_write_text

DRAFT_MAX_AGE_DAYS = 7
RETENTION_DAYS = {"ephemeral": 1, "standard": 30, "extended": 365}


def draft_ttl_days(retention_policy: str = "standard") -> int:
    """计算草稿 TTL 天数。

    Args:
        retention_policy: `retention_policy` 输入参数，类型为 str。

    Returns:
        函数处理结果，类型为 int。

    """
    policy_days = RETENTION_DAYS.get(str(retention_policy), 30)
    return max(1, min(DRAFT_MAX_AGE_DAYS, policy_days))


def _draft_dir(save_dir: Path) -> Path:
    """内部辅助：返回并创建草稿目录。

    Args:
        save_dir: `save_dir` 输入参数，类型为 Path。

    Returns:
        函数处理结果，类型为 Path。

    """
    path = save_dir / "drafts"
    path.mkdir(parents=True, exist_ok=True)
    return path


def draft_path(save_dir: Path, session_id: str) -> Path:
    """返回指定会话的草稿路径。

    Args:
        save_dir: `save_dir` 输入参数，类型为 Path。
        session_id: `session_id` 输入参数，类型为 str。

    Returns:
        函数处理结果，类型为 Path。

    Raises:
        ValueError: 当输入、状态或外部依赖不满足要求时抛出 ValueError。

    """
    safe_id = "".join(char for char in str(session_id) if char.isalnum() or char in "-_")
    if not safe_id:
        raise ValueError("session_id must contain at least one safe character")
    return _draft_dir(save_dir) / f"{safe_id}.json"


def save_interview_draft(save_dir: Path, data: dict[str, Any]) -> Path:
    """保存面试草稿并写入 TTL。

    Args:
        save_dir: `save_dir` 输入参数，类型为 Path。
        data: `data` 输入参数，类型为 dict[str, Any]。

    Returns:
        函数处理结果，类型为 Path。

    Raises:
        ValueError: 当输入、状态或外部依赖不满足要求时抛出 ValueError。

    """
    session_id = str(data.get("session_id", "")).strip()
    if not session_id:
        raise ValueError("draft requires session_id")
    payload = dict(data)
    ttl_days = draft_ttl_days(str(payload.get("retention_policy", "standard")))
    payload["draft_expires_at"] = (
        datetime.now(timezone.utc) + timedelta(days=ttl_days)
    ).isoformat()
    path = draft_path(save_dir, session_id)
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2))
    return path


def load_interview_draft(save_dir: Path, session_id: str) -> dict[str, Any] | None:
    """读取指定会话的草稿。

    Args:
        save_dir: `save_dir` 输入参数，类型为 Path。
        session_id: `session_id` 输入参数，类型为 str。

    Returns:
        函数处理结果，类型为 dict[str, Any] | None。

    """
    path = draft_path(save_dir, session_id)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def cleanup_expired_drafts(save_dir: Path) -> int:
    """删除过期草稿并返回数量。

    Args:
        save_dir: `save_dir` 输入参数，类型为 Path。

    Returns:
        函数处理结果，类型为 int。

    """
    directory = _draft_dir(save_dir)
    now = datetime.now(timezone.utc)
    removed = 0
    for path in directory.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            expires_at = str(data.get("draft_expires_at") or "")
            if expires_at:
                expired = datetime.fromisoformat(expires_at) <= now
            else:
                ttl_days = draft_ttl_days(str(data.get("retention_policy", "standard")))
                modified_at = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
                expired = modified_at + timedelta(days=ttl_days) <= now
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            expired = True
        if expired:
            try:
                path.unlink()
                removed += 1
            except FileNotFoundError:
                continue
    return removed


def latest_interview_draft(
    save_dir: Path,
    *,
    require_answers: bool = True,
) -> dict[str, Any] | None:
    """返回最新的可恢复面试草稿。

    Args:
        save_dir: `save_dir` 输入参数，类型为 Path。
        require_answers: `require_answers` 关键字参数，类型为 bool。

    Returns:
        函数处理结果，类型为 dict[str, Any] | None。

    """
    cleanup_expired_drafts(save_dir)
    directory = _draft_dir(save_dir)
    try:
        files = sorted(
            directory.glob("*.json"),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )
    except OSError:
        return None
    for path in files:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict) or not data.get("session_id"):
            continue
        if require_answers and len(data.get("messages") or []) < 2:
            continue
        return data
    return None


def delete_interview_draft(save_dir: Path, session_id: str) -> None:
    """删除指定会话的草稿。

    Args:
        save_dir: `save_dir` 输入参数，类型为 Path。
        session_id: `session_id` 输入参数，类型为 str。

    """
    path = draft_path(save_dir, session_id)
    try:
        path.unlink()
    except FileNotFoundError:
        return
