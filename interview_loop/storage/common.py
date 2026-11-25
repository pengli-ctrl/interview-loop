from pathlib import Path
from uuid import uuid4


def atomic_write_text(path: Path, text: str) -> None:
    temp_path = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    temp_path.write_text(text, encoding="utf-8")
    temp_path.replace(path)
