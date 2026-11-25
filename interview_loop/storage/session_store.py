import json
import time
from pathlib import Path

from interview_loop.storage.common import atomic_write_text


def new_session_id() -> str:
    return f"session_{int(time.time() * 1000)}"


def list_session_files(save_dir: Path) -> list[Path]:
    try:
        return sorted(save_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    except OSError:
        return []


def build_session_data(
    *,
    session_id: str,
    mode: str,
    interview_type: str,
    style: str,
    messages: list[dict],
    feedback: str,
    tags: list[str],
    started_at: str,
    completed_at: str,
    duration_seconds: int | None,
) -> dict:
    return {
        "time": started_at.replace("_", " "),
        "started_at": started_at,
        "completed_at": completed_at,
        "duration_seconds": duration_seconds,
        "session_id": session_id,
        "mode": mode,
        "interview_type": interview_type,
        "style": style,
        "messages": messages,
        "feedback": feedback,
        "tags": tags,
    }


def save_session_json(save_dir: Path, data: dict) -> Path:
    path = save_dir / f"{data['session_id']}.json"
    atomic_write_text(path, json.dumps(data, ensure_ascii=False, indent=2))
    return path
