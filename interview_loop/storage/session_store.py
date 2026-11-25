"""会话存储模块，负责会话 ID、JSON 数据和文件列表管理。"""
import json
import time
from pathlib import Path

from interview_loop.storage.common import atomic_write_text


def new_session_id() -> str:
    """生成会话 ID。

    Returns:
        函数处理结果，类型为 str。

    """
    return f"session_{int(time.time() * 1000)}"


def list_session_files(save_dir: Path) -> list[Path]:
    """列出会话 JSON 文件。

    Args:
        save_dir: `save_dir` 输入参数，类型为 Path。

    Returns:
        函数处理结果，类型为 list[Path]。

    """
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
    job_description: str = "",
    job_match: dict | None = None,
    structured_report: dict | None = None,
    tenant_id: str = "local",
    user_id: str = "local",
    trace_id: str | None = None,
    consent_granted: bool = False,
    consent_at: str | None = None,
    retention_policy: str = "standard",
    retention_expires_at: str | None = None,
) -> dict:
    """构建会话 JSON 数据。

    Args:
        session_id: `session_id` 关键字参数，类型为 str。
        mode: `mode` 关键字参数，类型为 str。
        interview_type: `interview_type` 关键字参数，类型为 str。
        style: `style` 关键字参数，类型为 str。
        messages: `messages` 关键字参数，类型为 list[dict]。
        feedback: `feedback` 关键字参数，类型为 str。
        tags: `tags` 关键字参数，类型为 list[str]。
        started_at: `started_at` 关键字参数，类型为 str。
        completed_at: `completed_at` 关键字参数，类型为 str。
        duration_seconds: `duration_seconds` 关键字参数，类型为 int | None。
        job_description: `job_description` 关键字参数，类型为 str。
        job_match: `job_match` 关键字参数，类型为 dict | None。
        structured_report: `structured_report` 关键字参数，类型为 dict | None。
        tenant_id: `tenant_id` 关键字参数，类型为 str。
        user_id: `user_id` 关键字参数，类型为 str。
        trace_id: `trace_id` 关键字参数，类型为 str | None。
        consent_granted: `consent_granted` 关键字参数，类型为 bool。
        consent_at: `consent_at` 关键字参数，类型为 str | None。
        retention_policy: `retention_policy` 关键字参数，类型为 str。
        retention_expires_at: `retention_expires_at` 关键字参数，类型为 str | None。

    Returns:
        函数处理结果，类型为 dict。

    """
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
        "job_description": job_description,
        "job_match": job_match or {},
        "structured_report": structured_report or {},
        "tenant_id": tenant_id,
        "user_id": user_id,
        "trace_id": trace_id,
        "consent_granted": consent_granted,
        "consent_at": consent_at,
        "retention_policy": retention_policy,
        "retention_expires_at": retention_expires_at,
    }


def save_session_json(save_dir: Path, data: dict) -> Path:
    """保存会话 JSON。

    Args:
        save_dir: `save_dir` 输入参数，类型为 Path。
        data: `data` 输入参数，类型为 dict。

    Returns:
        函数处理结果，类型为 Path。

    """
    path = save_dir / f"{data['session_id']}.json"
    atomic_write_text(path, json.dumps(data, ensure_ascii=False, indent=2))
    return path
