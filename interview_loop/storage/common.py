"""存储公共模块，负责原子写入等文件持久化辅助。"""
from pathlib import Path
from uuid import uuid4


def atomic_write_text(path: Path, text: str) -> None:
    """原子写入文本文件。

    Args:
        path: `path` 输入参数，类型为 Path。
        text: `text` 输入参数，类型为 str。

    """
    temp_path = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    temp_path.write_text(text, encoding="utf-8")
    temp_path.replace(path)
