"""Per-job STT/TTS metadata on disk (00_job_meta.json)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

META_NAME = "00_job_meta.json"


def meta_path(job_folder: str | Path) -> Path:
    return Path(job_folder) / META_NAME


def read_meta(job_folder: str | Path) -> dict[str, Any]:
    path = meta_path(job_folder)
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def write_meta(job_folder: str | Path, data: dict[str, Any]) -> Path:
    folder = Path(job_folder)
    folder.mkdir(parents=True, exist_ok=True)
    path = meta_path(folder)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def merge_meta(job_folder: str | Path, patch: dict[str, Any]) -> dict[str, Any]:
    current = read_meta(job_folder)
    current.update({k: v for k, v in patch.items() if v is not None})
    write_meta(job_folder, current)
    return current
