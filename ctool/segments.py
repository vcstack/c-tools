"""Edit / delete transcript sentences and keep SQLite + TTS in sync."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ctool.store import (
    JOB_STATUS_STT,
    assert_job_editable,
    connect,
    db_path,
    job_dir,
    load_transcript,
    load_tts_manifest,
    save_tts_job,
)


def segment_uid(seg: dict[str, Any], index: int) -> str:
    uid = (seg.get("id") or "").strip()
    return uid or f"u{index:04d}"


def ensure_segment_ids(payload: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    changed = False
    used: set[str] = set()
    segs = list(payload.get("segments") or [])
    for seg in segs:
        uid = (seg.get("id") or "").strip()
        if uid:
            used.add(uid)
    n = 0
    for i, seg in enumerate(segs):
        uid = (seg.get("id") or "").strip()
        if uid:
            continue
        while True:
            cand = f"u{n:04d}"
            n += 1
            if cand not in used:
                break
        seg["id"] = cand
        used.add(cand)
        changed = True
    payload["segments"] = segs
    return payload, changed


def list_segment_records(job_id: str, root: str | Path | None = None) -> list[dict[str, Any]]:
    payload = load_and_persist_ids(job_id, root)
    manifest = load_tts_manifest(job_id, root) or {}
    done = {it.get("id") for it in (manifest.get("items") or []) if it.get("id")}
    last_voice = {
        it.get("id"): (it.get("voice") or "").strip()
        for it in (manifest.get("items") or [])
        if it.get("id")
    }
    out: list[dict[str, Any]] = []
    for i, seg in enumerate(payload.get("segments") or []):
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        uid = segment_uid(seg, i)
        out.append(
            {
                "id": uid,
                "speaker": seg.get("speaker") or "SPEAKER_00",
                "start": float(seg.get("start") or 0),
                "end": float(seg.get("end") or 0),
                "text": text,
                "tts": "✓ TTS" if uid in done else "—",
                "voice": last_voice.get(uid) or "",
            }
        )
    return out


def load_and_persist_ids(job_id: str, root: str | Path | None = None) -> dict[str, Any]:
    payload = load_transcript(job_id, root=root)
    payload, changed = ensure_segment_ids(payload)
    if changed:
        _persist_payload(job_id, payload, root, sync_db=True)
    return payload


def update_segment_text(
    job_id: str,
    uid: str,
    text: str,
    root: str | Path | None = None,
) -> dict[str, Any]:
    assert_job_editable(job_id, root)
    new_text = (text or "").strip()
    if not new_text:
        raise ValueError("Nội dung câu không được trống.")
    payload = load_and_persist_ids(job_id, root)
    found = False
    for i, seg in enumerate(payload.get("segments") or []):
        if segment_uid(seg, i) == uid:
            seg["text"] = new_text
            found = True
            break
    if not found:
        raise ValueError(f"Không thấy câu {uid}.")
    _persist_payload(job_id, payload, root, sync_db=True)
    return payload


def delete_segment(job_id: str, uid: str, root: str | Path | None = None) -> dict[str, Any]:
    assert_job_editable(job_id, root)
    payload = load_and_persist_ids(job_id, root)
    kept: list[dict[str, Any]] = []
    found = False
    for i, seg in enumerate(payload.get("segments") or []):
        if segment_uid(seg, i) == uid:
            found = True
            continue
        kept.append(seg)
    if not found:
        raise ValueError(f"Không thấy câu {uid}.")
    if not kept:
        raise ValueError("Không xóa hết mọi câu — job phải còn ít nhất 1 câu.")
    payload["segments"] = kept
    payload["speakers"] = sorted({s.get("speaker") or "SPEAKER_00" for s in kept})
    _persist_payload(job_id, payload, root, sync_db=True)
    _drop_tts_item(job_id, uid, root)
    return payload


def _persist_payload(
    job_id: str,
    payload: dict[str, Any],
    root: str | Path | None,
    *,
    sync_db: bool,
) -> None:
    folder = job_dir(job_id, root)
    path = folder / "01_transcript.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if not sync_db or not db_path(root).is_file():
        return
    speakers = list(payload.get("speakers") or [])
    segments = list(payload.get("segments") or [])
    if not speakers:
        speakers = sorted({s.get("speaker") or "SPEAKER_00" for s in segments})
    with connect(root) as conn:
        conn.execute("DELETE FROM segments WHERE job_id = ?", (job_id,))
        conn.execute("DELETE FROM speakers WHERE job_id = ?", (job_id,))
        speaker_ids: dict[str, int] = {}
        for label in speakers:
            cur = conn.execute(
                "INSERT INTO speakers (job_id, label, display_name) VALUES (?, ?, ?)",
                (job_id, label, None),
            )
            speaker_ids[label] = int(cur.lastrowid)
        for seg in segments:
            label = seg.get("speaker") or "SPEAKER_00"
            if label not in speaker_ids:
                cur = conn.execute(
                    "INSERT INTO speakers (job_id, label, display_name) VALUES (?, ?, ?)",
                    (job_id, label, None),
                )
                speaker_ids[label] = int(cur.lastrowid)
            conn.execute(
                """
                INSERT INTO segments (job_id, speaker_id, start_sec, end_sec, text)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    speaker_ids[label],
                    float(seg.get("start") or 0),
                    float(seg.get("end") or 0),
                    (seg.get("text") or "").strip(),
                ),
            )
        conn.execute(
            "UPDATE jobs SET transcript_path = ? WHERE id = ?",
            (str(path), job_id),
        )
        conn.commit()


def _drop_tts_item(job_id: str, uid: str, root: str | Path | None) -> None:
    from ctool.tts_job import _concat_ffmpeg

    manifest = load_tts_manifest(job_id, root)
    if not manifest:
        return
    folder = job_dir(job_id, root)
    leftover: list[dict[str, Any]] = []
    for item in manifest.get("items") or []:
        if item.get("id") == uid:
            rel = item.get("audio") or ""
            path = folder / rel if rel else folder / "tts" / f"{uid}.mp3"
            if path.is_file():
                try:
                    path.unlink()
                except OSError:
                    pass
            continue
        leftover.append(item)
    if not leftover:
        tts_json = folder / "03_tts.json"
        if tts_json.is_file():
            try:
                tts_json.unlink()
            except OSError:
                pass
        if db_path(root).is_file():
            with connect(root) as conn:
                conn.execute(
                    "UPDATE jobs SET status = ?, tts_path = NULL WHERE id = ?",
                    (JOB_STATUS_STT, job_id),
                )
                conn.commit()
        return
    audio_files: list[Path] = []
    for item in leftover:
        rel = item.get("audio") or ""
        path = folder / rel if rel else None
        if path and path.is_file():
            audio_files.append(path)
    merged = _concat_ffmpeg(audio_files, folder / "tts_full") if audio_files else None
    manifest["items"] = leftover
    if merged:
        manifest["audio"] = str(merged.relative_to(folder)).replace("\\", "/")
    save_tts_job(job_id, manifest, root)
