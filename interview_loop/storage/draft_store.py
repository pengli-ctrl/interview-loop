import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from interview_loop.storage.common import atomic_write_text

DRAFT_MAX_AGE_DAYS = 7
RETENTION_DAYS = {"ephemeral": 1, "standard": 30, "extended": 365}


def draft_ttl_days(retention_policy: str = "standard") -> int:
    policy_days = RETENTION_DAYS.get(str(retention_policy), 30)
    return max(1, min(DRAFT_MAX_AGE_DAYS, policy_days))


def _draft_dir(save_dir: Path) -> Path:
    path = save_dir / "drafts"
    path.mkdir(parents=True, exist_ok=True)
    return path


def draft_path(save_dir: Path, session_id: str) -> Path:
    safe_id = "".join(char for char in str(session_id) if char.isalnum() or char in "-_")
    if not safe_id:
        raise ValueError("session_id must contain at least one safe character")
    return _draft_dir(save_dir) / f"{safe_id}.json"


def save_interview_draft(save_dir: Path, data: dict[str, Any]) -> Path:
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
    path = draft_path(save_dir, session_id)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def cleanup_expired_drafts(save_dir: Path) -> int:
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
    path = draft_path(save_dir, session_id)
    try:
        path.unlink()
    except FileNotFoundError:
        return
