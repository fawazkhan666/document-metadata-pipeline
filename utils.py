import json
import re
from pathlib import Path
from typing import Iterable, Union


PathLike = Union[str, Path]


def ensure_directories(paths: Iterable[PathLike]) -> None:
    for path in paths:
        Path(path).mkdir(parents=True, exist_ok=True)


def safe_filename(name: str) -> str:
    cleaned = re.sub(r"[\\/:*?\"<>|]+", "_", name).strip()
    return cleaned or "untitled"


def write_json(path: PathLike, data: object) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_context(text: str) -> str:
    lines = text.splitlines()
    if not lines:
        return ""

    first_indices = list(range(0, min(10, len(lines))))
    last_start = max(len(lines) - 10, 0)
    last_indices = list(range(last_start, len(lines)))

    total = len(lines)
    middle_start = max((total // 2) - 5, 0)
    middle_end = min(middle_start + 10, total)
    middle_indices = list(range(middle_start, middle_end))

    selected = []
    seen = set()
    for segment in (first_indices, middle_indices, last_indices):
        for idx in segment:
            if idx in seen:
                continue
            selected.append(lines[idx])
            seen.add(idx)

    return "\n".join(selected).strip()
