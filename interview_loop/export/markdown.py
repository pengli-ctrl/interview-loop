from pathlib import Path

from interview_loop.storage.common import atomic_write_text


def safe_filename_part(value: str) -> str:
    invalid = '<>:"/\\|?*'
    cleaned = "".join("_" if char in invalid or ord(char) < 32 else char for char in str(value))
    return cleaned.strip(" .") or "未命名"


def format_duration(seconds: int | None) -> str:
    if seconds is None:
        return "未记录"
    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}小时{minutes}分{secs}秒"
    if minutes:
        return f"{minutes}分{secs}秒"
    return f"{secs}秒"


def build_markdown_record(data: dict) -> str:
    lines = [
        "# 面试记录",
        "",
        f"- 面试开始时间：{data.get('started_at', '未知')}",
        f"- 面试结束时间：{data.get('completed_at', '未知')}",
        f"- 面试轮次：{data.get('mode', '未知')}",
        f"- 面试模式：{data.get('interview_type', '未知')}",
        f"- 面试风格：{data.get('style', '未知')}",
        f"- 面试时长：{format_duration(data.get('duration_seconds'))}",
        f"- 会话 ID：{data.get('session_id', '未知')}",
        "",
        "## 面试对话",
        "",
    ]

    turns = []
    pending_question = ""
    for message in data.get("messages", []):
        role = message.get("role")
        content = str(message.get("content", "")).strip()
        if role == "interviewer":
            if pending_question:
                turns.append((pending_question, ""))
            pending_question = content
        elif role == "candidate":
            turns.append((pending_question, content))
            pending_question = ""
    if pending_question:
        turns.append((pending_question, ""))

    if not turns:
        lines.extend(["暂无对话记录。", ""])
    for index, (question, answer) in enumerate(turns, start=1):
        lines.extend(
            [
                f"### 第 {index} 题",
                "",
                "**面试官：**",
                "",
                question or "（未记录）",
                "",
                "**候选人：**",
                "",
                answer or "（未回答）",
                "",
            ]
        )

    lines.extend(
        [
            "## 面试复盘报告",
            "",
            str(data.get("feedback") or "暂无复盘报告").strip(),
            "",
            "## 薄弱标签",
            "",
        ]
    )
    tags = data.get("tags") or []
    if tags:
        lines.extend(f"- {tag}" for tag in tags)
    else:
        lines.append("暂无标签")
    lines.append("")
    return "\n".join(lines)


def save_markdown_record(record_dir: Path, data: dict) -> tuple[Path, str]:
    filename = "_".join(
        [
            safe_filename_part(data.get("started_at", "未知")),
            safe_filename_part(data.get("mode", "未知")),
            safe_filename_part(data.get("interview_type", "未知")),
            safe_filename_part(data.get("style", "未知")),
        ]
    ) + ".md"
    path = record_dir / filename
    markdown = build_markdown_record(data)
    atomic_write_text(path, markdown)
    return path, markdown
