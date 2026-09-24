"""Build 03_tts.json + audio from a transcript via VieNeu Cloud V4."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from ctool.store import (
    assert_job_editable,
    job_dir,
    load_tts_manifest,
    load_transcript,
    new_job_id,
    resolve_store_root,
    save_tts_job,
)
from ctool.vieneu import synthesize


def parse_voice_map(text: str | None, default_voice: str) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for line in (text or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        if key and value:
            mapping[key] = value
    mapping.setdefault("SPEAKER_00", default_voice)
    return mapping


def _concat_ffmpeg(files: list[Path], dest: Path) -> Path | None:
    if not files:
        return None
    if len(files) == 1:
        out = dest.with_suffix(files[0].suffix)
        shutil.copyfile(files[0], out)
        return out
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return files[0]
    lst = dest.parent / "concat.txt"
    lines = []
    for path in files:
        escaped = str(path.resolve()).replace("'", r"'\''")
        lines.append(f"file '{escaped}'")
    lst.write_text("\n".join(lines) + "\n", encoding="utf-8")
    out = dest.with_suffix(files[0].suffix)
    cmd = [
        ffmpeg,
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(lst),
        "-c",
        "copy",
        str(out),
    ]
    if subprocess.call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) != 0:
        cmd[-3] = str(out.with_suffix(".wav"))
        cmd[-2] = "pcm_s16le"
        # rebuild without -c copy
        cmd = [
            ffmpeg,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(lst),
            str(out.with_suffix(".wav")),
        ]
        if subprocess.call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) != 0:
            return files[0]
        return out.with_suffix(".wav")
    return out


def run_vieneu_tts(
    api_key: str,
    *,
    job_id: str | None = None,
    json_path: str | Path | None = None,
    default_voice: str = "Ngọc Lan",
    voice_map_text: str | None = None,
    voice_map: dict[str, str] | None = None,
    only_speakers: list[str] | None = None,
    single_voice: str | None = None,
    only_item_ids: list[str] | None = None,
    store_root: str | Path | None = None,
) -> dict[str, Any]:
    key = (api_key or "").strip() or os.environ.get("VIENEU_API_KEY", "").strip()
    if not key:
        raise ValueError("Cần VieNeu API key (https://www.vieneu.io/ — Cloud V4).")

    payload = load_transcript(job_id, json_path, store_root)
    jid = (payload.get("job_id") or job_id or "").strip()
    if not jid:
        fname = (payload.get("source") or {}).get("filename") or "tts"
        jid = new_job_id(fname)
        payload["job_id"] = jid
    elif job_id:
        assert_job_editable(jid, store_root)

    root = resolve_store_root(store_root)
    folder = job_dir(jid, root)
    tts_dir = folder / "tts"
    tts_dir.mkdir(parents=True, exist_ok=True)

    voices = parse_voice_map(voice_map_text, default_voice or "Ngọc Lan")
    if voice_map:
        voices.update({k: v.strip() for k, v in voice_map.items() if (v or "").strip()})

    existing = load_tts_manifest(jid, root) or {}
    regen_ids = {x.strip() for x in (only_item_ids or []) if (x or "").strip()} or None
    partial = bool(regen_ids)

    from ctool.segments import ensure_segment_ids, segment_uid

    payload, _ = ensure_segment_ids(payload)
    allow = {s for s in (only_speakers or []) if s} or None
    new_by_id: dict[str, dict[str, Any]] = {}
    for i, seg in enumerate(payload.get("segments") or []):
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        uid = segment_uid(seg, i)
        if regen_ids and uid not in regen_ids:
            continue
        speaker = seg.get("speaker") or "SPEAKER_00"
        if allow and speaker not in allow:
            continue
        voice = (single_voice or "").strip() or voices.get(speaker) or default_voice or "Ngọc Lan"
        dest = tts_dir / f"{uid}.mp3"
        print(f"VieNeu V4 {uid} {speaker} → {voice}")
        audio = synthesize(key, text, voice, dest=dest)
        new_by_id[uid] = {
            "id": uid,
            "speaker": speaker,
            "voice": voice,
            "text": text,
            "audio": str(audio.relative_to(folder)).replace("\\", "/"),
            "ref_start": seg.get("start"),
            "ref_end": seg.get("end"),
        }

    if partial:
        merged_items: dict[str, dict[str, Any]] = {
            it["id"]: it for it in (existing.get("items") or []) if it.get("id")
        }
        merged_items.update(new_by_id)
        items = [merged_items[k] for k in sorted(merged_items.keys())]
    else:
        items = [new_by_id[k] for k in sorted(new_by_id.keys())]

    if not items:
        raise ValueError("Không có segment text để TTS.")

    audio_files: list[Path] = []
    for item in items:
        rel = item.get("audio") or ""
        path = folder / rel if rel else None
        if path and path.is_file():
            audio_files.append(path)

    merged = _concat_ffmpeg(audio_files, folder / "tts_full")
    manifest: dict[str, Any] = {
        "job_id": jid,
        "from": "01_transcript.json",
        "engine": "vieneu-v4-cloud",
        "default_voice": default_voice,
        "voices": voices,
        "items": items,
    }
    if merged:
        manifest["audio"] = str(merged.relative_to(folder)).replace("\\", "/")
    path = save_tts_job(jid, manifest, root)
    manifest["store"] = {"tts_json": str(path), "job_dir": str(folder)}
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest
