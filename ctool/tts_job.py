"""Build 03_tts.json + audio from a transcript via VieNeu Cloud V4."""

from __future__ import annotations

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
from ctool.vieneu import is_key_limit_error, synthesize


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


def clip_filename(index: int, uid: str) -> str:
    """00000_s0000.mp3 — prefix cố định độ rộng, sort tên file đúng thứ tự câu."""
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in (uid or "")) or "clip"
    return f"{index:05d}_{safe}.mp3"


def _audio_ok(path: Path) -> bool:
    try:
        return path.is_file() and path.stat().st_size >= 32
    except OSError:
        return False


def find_clip(folder: Path, index: int, uid: str) -> Path | None:
    stem = Path(clip_filename(index, uid)).stem
    for ext in (".mp3", ".wav"):
        path = folder / f"{stem}{ext}"
        if _audio_ok(path):
            return path
    for ext in (".mp3", ".wav"):
        legacy = folder / f"{uid}{ext}"
        if _audio_ok(legacy):
            return legacy
    return None


def _concat_ffmpeg(files: list[Path], dest: Path) -> Path | None:
    files = [path for path in files if _audio_ok(path)]
    if not files:
        return None
    if dest.suffix.lower() in {".mp3", ".wav"}:
        out = dest
    else:
        out = dest.with_suffix(files[0].suffix)
    out.parent.mkdir(parents=True, exist_ok=True)
    if len(files) == 1:
        if files[0].resolve() != out.resolve():
            shutil.copyfile(files[0], out)
        return out
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return None
    lst = out.with_name(out.stem + ".concat.txt")
    lines = []
    for path in files:
        posix = path.resolve().as_posix().replace("'", r"'\''")
        lines.append(f"file '{posix}'")
    lst.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        copy_cmd = [
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
        if subprocess.call(copy_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0:
            return out
        wav = out.with_suffix(".wav")
        wav_cmd = [
            ffmpeg,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(lst),
            str(wav),
        ]
        if subprocess.call(wav_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) != 0:
            return None
        return wav
    finally:
        try:
            lst.unlink(missing_ok=True)
        except OSError:
            pass


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

    from ctool.segments import ensure_segment_ids, segment_uid

    payload, _ = ensure_segment_ids(payload)
    allow = {s for s in (only_speakers or []) if s} or None
    by_id: dict[str, dict[str, Any]] = {
        it["id"]: it for it in (existing.get("items") or []) if it.get("id")
    }
    order: dict[str, int] = {}
    targets: list[tuple[int, str, str, str, str, dict[str, Any]]] = []
    for i, seg in enumerate(payload.get("segments") or []):
        if not isinstance(seg, dict):
            continue
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        uid = segment_uid(seg, i)
        order[uid] = i
        speaker = seg.get("speaker") or "SPEAKER_00"
        if allow and speaker not in allow:
            continue
        voice = (single_voice or "").strip() or voices.get(speaker) or default_voice or "Ngọc Lan"
        targets.append((i, uid, speaker, voice, text, seg))

    if not targets:
        raise ValueError("Không có segment text để TTS.")

    for name in ("final.mp3", "final.wav"):
        stale = folder / name
        if stale.is_file():
            try:
                stale.unlink()
            except OSError:
                pass

    def _persist(merged_path: Path | None = None) -> dict[str, Any]:
        items = sorted(by_id.values(), key=lambda it: (order.get(it["id"], 10**9), it["id"]))
        manifest: dict[str, Any] = {
            "job_id": jid,
            "from": "01_transcript.json",
            "engine": "vieneu-v4-cloud",
            "default_voice": default_voice,
            "voices": voices,
            "items": items,
        }
        if merged_path and merged_path.is_file():
            manifest["audio"] = str(merged_path.relative_to(folder)).replace("\\", "/")
        path = save_tts_job(jid, manifest, root)
        manifest["store"] = {"tts_json": str(path), "job_dir": str(folder)}
        return manifest

    for i, uid, speaker, voice, text, seg in targets:
        if regen_ids and uid not in regen_ids:
            continue
        prev = by_id.get(uid) or {}
        same_text = (prev.get("text") or text) == text
        dest = tts_dir / clip_filename(i, uid)
        audio: Path | None = None
        forced = bool(regen_ids and uid in regen_ids)
        if not forced and same_text:
            audio = find_clip(tts_dir, i, uid)
            indexed = dest.with_suffix(audio.suffix) if audio else dest
            if audio and audio.resolve() != indexed.resolve() and not _audio_ok(indexed):
                shutil.copyfile(audio, indexed)
                audio = indexed
        if audio is None or not _audio_ok(audio):
            print(f"VieNeu V4 {dest.name} {speaker} → {voice}")
            try:
                audio = synthesize(key, text, voice, dest=dest)
            except Exception as exc:
                _persist()
                if is_key_limit_error(str(exc)):
                    raise RuntimeError(
                        f"Hết hạn mức token VieNeu tại {dest.name}. "
                        "Các câu đã gen vẫn giữ. Đổi API key rồi chạy lại để nối tiếp."
                    ) from exc
                raise
        rel = str(audio.relative_to(folder)).replace("\\", "/")
        by_id[uid] = {
            "id": uid,
            "index": i,
            "speaker": speaker,
            "voice": voice,
            "text": text,
            "audio": rel,
            "ref_start": seg.get("start"),
            "ref_end": seg.get("end"),
        }
        _persist()

    ready: list[Path] = []
    for i, uid, _speaker, _voice, _text, _seg in targets:
        item = by_id.get(uid) or {}
        rel = item.get("audio") or ""
        path = folder / rel if rel else None
        if not path or not _audio_ok(path):
            path = find_clip(tts_dir, i, uid)
        if not path:
            manifest = _persist()
            manifest["final_pending"] = uid
            return manifest
        ready.append(path)

    merged = _concat_ffmpeg(ready, folder / "final.mp3")
    manifest = _persist(merged)
    if not merged:
        manifest["final_error"] = "Đã lưu từng câu. Thiếu ffmpeg hoặc ghép final lỗi."
    return manifest
