import json
from pathlib import Path
from typing import Any

from interview_loop.storage.common import atomic_write_text


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
    path = draft_path(save_dir, session_id)
    atomic_write_text(path, json.dumps(data, ensure_ascii=False, indent=2))
    return path


def load_interview_draft(save_dir: Path, session_id: str) -> dict[str, Any] | None:
    path = draft_path(save_dir, session_id)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def latest_interview_draft(save_dir: Path) -> dict[str, Any] | None:
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
        if isinstance(data, dict) and data.get("session_id"):
            return data
    return None


def delete_interview_draft(save_dir: Path, session_id: str) -> None:
    path = draft_path(save_dir, session_id)
    try:
        path.unlink()
    except FileNotFoundError:
        return
