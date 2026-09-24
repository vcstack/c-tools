"""App prefs in SQLite table `settings` (same ctool.db as jobs)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ctool.store import connect, resolve_store_root

DEFAULTS = {
    "vieneu_api_key": "",
    "voice_0": "Ngọc Lan",
    "voice_1": "Phạm Tuyên",
    "tts_count": "1",
    "one_mode": "Cả file",
    "sample_text": "Xin chào, đây là giọng VieNeu V4.",
}


def _legacy_json(root: str | Path | None) -> dict[str, Any]:
    path = resolve_store_root(root) / "settings.json"
    if not path.is_file():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
        return loaded if isinstance(loaded, dict) else {}
    except Exception:
        return {}


def load_settings(root: str | Path | None = None) -> dict[str, Any]:
    data = dict(DEFAULTS)
    with connect(root) as conn:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
    if not rows:
        data.update({k: v for k, v in _legacy_json(root).items() if k in DEFAULTS and v})
        return data
    for row in rows:
        if row["key"] in data and row["value"] is not None:
            data[row["key"]] = row["value"]
    return data


def save_settings(
    *,
    vieneu_api_key: str | None = None,
    voice_0: str | None = None,
    voice_1: str | None = None,
    tts_count: str | int | None = None,
    one_mode: str | None = None,
    sample_text: str | None = None,
    root: str | Path | None = None,
) -> dict[str, Any]:
    data = load_settings(root)
    if vieneu_api_key is not None:
        data["vieneu_api_key"] = vieneu_api_key.strip()
    if voice_0 is not None and str(voice_0).strip():
        data["voice_0"] = str(voice_0).strip()
    if voice_1 is not None and str(voice_1).strip():
        data["voice_1"] = str(voice_1).strip()
    if tts_count is not None:
        data["tts_count"] = "2" if str(tts_count).strip() in ("2", "2 speakers") else "1"
    if one_mode is not None and str(one_mode).strip():
        data["one_mode"] = str(one_mode).strip()
    if sample_text is not None and sample_text.strip():
        data["sample_text"] = sample_text.strip()
    with connect(root) as conn:
        for key, value in data.items():
            conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )
        conn.commit()
    return data


def speakers_from_payload(payload: dict[str, Any]) -> list[str]:
    names = [str(s) for s in (payload.get("speakers") or []) if s]
    if not names:
        seen = []
        for seg in payload.get("segments") or []:
            label = seg.get("speaker") or "SPEAKER_00"
            if label not in seen:
                seen.append(label)
        names = seen
    return names[:2] or ["SPEAKER_00"]
