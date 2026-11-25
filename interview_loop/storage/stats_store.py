"""统计存储模块，负责薄弱标签统计的读写和容错。"""
import json
from pathlib import Path

from interview_loop.storage.common import atomic_write_text


def load_stats(path: Path, modes: list[str]) -> tuple[dict, str | None]:
    """加载薄弱统计。

    Args:
        path: `path` 输入参数，类型为 Path。
        modes: `modes` 输入参数，类型为 list[str]。

    Returns:
        函数处理结果，类型为 tuple[dict, str | None]。

    """
    empty_stats = {mode: {} for mode in modes}
    if not path.exists():
        return empty_stats, None

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return empty_stats, str(exc)

    if not isinstance(raw, dict):
        return empty_stats, None

    stats = {}
    for mode in modes:
        mode_stats = raw.get(mode, {})
        if not isinstance(mode_stats, dict):
            mode_stats = {}
        cleaned = {}
        for tag, count in mode_stats.items():
            try:
                cleaned[str(tag)] = max(0, int(count))
            except (TypeError, ValueError):
                continue
        stats[mode] = cleaned
    return stats, None


def save_stats(path: Path, stats: dict) -> None:
    """保存薄弱统计。

    Args:
        path: `path` 输入参数，类型为 Path。
        stats: `stats` 输入参数，类型为 dict。

    """
    atomic_write_text(path, json.dumps(stats, ensure_ascii=False, indent=2))
