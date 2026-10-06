"""JSON kịch bản + sidecar TTS. Không phụ thuộc UI."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from ctool.tts_job import _concat_ffmpeg, clip_filename, concat_error, find_clip
from ctool.vieneu import brief_api_error, synthesize

STATUS_PENDING = "chưa"
STATUS_GEN = "đang gen"
STATUS_DONE = "xong"
STATUS_ERROR = "lỗi"
STATUS_STALE = "text đổi"


def state_path(json_path: Path) -> Path:
    return json_path.with_suffix(json_path.suffix + ".tts.json")


def audio_dir(json_path: Path) -> Path:
    return json_path.with_name(json_path.stem + ".tts")


def load_prefs() -> tuple[str, str]:
    key = (os.environ.get("VIENEU_API_KEY") or "").strip()
    voice = "Ngọc Lan"
    try:
        from ctool.settings import load_settings

        prefs = load_settings()
        key = (prefs.get("vieneu_api_key") or key).strip()
        voice = (prefs.get("voice_0") or voice).strip() or voice
    except Exception:
        pass
    return key, voice


def save_prefs(api_key: str, voice: str) -> None:
    try:
        from ctool.settings import save_settings

        save_settings(vieneu_api_key=api_key, voice_0=voice)
    except Exception:
        os.environ["VIENEU_API_KEY"] = api_key


class TtsProject:
    def __init__(self) -> None:
        self.json_path: Path | None = None
        self.payload: dict[str, Any] = {"speakers": ["SPEAKER_00"], "segments": []}
        self.items: dict[str, dict[str, Any]] = {}
        self.voice = "Ngọc Lan"
        self.final_path = ""
        self.final_error = ""
        self.merged_now: Path | None = None

    def segments(self) -> list[dict[str, Any]]:
        return [s for s in (self.payload.get("segments") or []) if isinstance(s, dict)]

    def ids(self) -> list[str]:
        return [str(s["id"]) for s in self.segments()]

    def segment(self, sid: str) -> dict[str, Any] | None:
        for seg in self.segments():
            if str(seg.get("id")) == sid:
                return seg
        return None

    def status_of(self, sid: str) -> str:
        return str((self.items.get(sid) or {}).get("status") or STATUS_PENDING)

    def audio_of(self, sid: str) -> Path | None:
        raw = (self.items.get(sid) or {}).get("audio") or ""
        path = Path(raw) if raw else None
        return path if path and path.is_file() else None

    def error_of(self, sid: str) -> str:
        return str((self.items.get(sid) or {}).get("error") or "")

    def counts(self) -> tuple[int, int, int]:
        segs = self.segments()
        n = len(segs)
        done = sum(1 for s in segs if self.status_of(str(s["id"])) == STATUS_DONE)
        err = sum(1 for s in segs if self.status_of(str(s["id"])) == STATUS_ERROR)
        return done, err, n

    def load(self, path: Path) -> None:
        raw = json.loads(path.read_text(encoding="utf-8"))
        segs = raw.get("segments")
        if not isinstance(segs, list):
            raise ValueError("Không thấy mảng segments.")
        for i, seg in enumerate(segs):
            if not isinstance(seg, dict):
                continue
            if not str(seg.get("id") or "").strip():
                seg["id"] = f"s{i:04d}"
            seg.setdefault("speaker", "SPEAKER_00")
            seg.setdefault("text", "")
        self.json_path = path
        self.payload = raw
        self.items = {}
        sidecar = state_path(path)
        if sidecar.is_file():
            try:
                saved = json.loads(sidecar.read_text(encoding="utf-8"))
                self.items = saved.get("items") or {}
                if saved.get("voice"):
                    self.voice = str(saved["voice"])
                self.final_path = str(saved.get("final") or "")
            except Exception:
                self.items = {}
        folder = audio_dir(path)
        for i, seg in enumerate(segs):
            sid = str(seg["id"])
            st = self.items.setdefault(
                sid, {"status": STATUS_PENDING, "audio": "", "error": ""}
            )
            audio = Path(st.get("audio") or "")
            if not audio.is_file():
                guess = find_clip(folder, i, sid)
                if guess:
                    st["audio"] = str(guess)
                    st["status"] = STATUS_DONE
            if (
                st.get("status") == STATUS_DONE
                and st.get("text_at_gen")
                and st["text_at_gen"] != (seg.get("text") or "").strip()
            ):
                st["status"] = STATUS_STALE

    def save_json(self) -> None:
        if not self.json_path:
            raise ValueError("Chưa mở file.")
        self.json_path.write_text(
            json.dumps(self.payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def flush_state(self) -> None:
        if not self.json_path:
            return
        state_path(self.json_path).write_text(
            json.dumps(
                {
                    "json_path": str(self.json_path),
                    "voice": self.voice,
                    "final": self.final_path,
                    "items": self.items,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    def set_text(self, sid: str, text: str) -> bool:
        seg = self.segment(sid)
        if not seg:
            return False
        text = text.rstrip("\n")
        if (seg.get("text") or "") == text:
            return False
        seg["text"] = text
        st = self.items.setdefault(sid, {"status": STATUS_PENDING, "audio": "", "error": ""})
        if st.get("status") == STATUS_DONE:
            st["status"] = STATUS_STALE
        self.save_json()
        self.flush_state()
        return True

    def todo(self, mode: str, current: str | None) -> list[str]:
        ids = self.ids()
        if not ids:
            return []
        cur = current if current in ids else ids[0]
        if mode == "one":
            return [cur]
        if mode == "from":
            start = ids.index(cur)
            return [sid for sid in ids[start:] if self.status_of(sid) != STATUS_DONE]
        return [sid for sid in ids if self.status_of(sid) != STATUS_DONE]

    def mark(self, sid: str, status: str, **extra: Any) -> None:
        row = self.items.setdefault(sid, {"status": STATUS_PENDING, "audio": "", "error": ""})
        row["status"] = status
        row.update(extra)
        self.flush_state()

    def synthesize_one(self, sid: str, api_key: str, voice: str) -> Path:
        if not self.json_path:
            raise ValueError("Chưa mở file.")
        seg = self.segment(sid)
        text = ((seg or {}).get("text") or "").strip()
        if not text:
            self.mark(sid, STATUS_ERROR, audio="", error="Trống text")
            raise ValueError("Trống text")
        self.voice = voice
        self._drop_final()
        self.mark(sid, STATUS_GEN)
        folder = audio_dir(self.json_path)
        folder.mkdir(parents=True, exist_ok=True)
        index = self.ids().index(sid)
        dest = folder / clip_filename(index, sid)
        try:
            path = synthesize(api_key, text, voice, dest=dest)
        except Exception as exc:
            prev = (self.items.get(sid) or {}).get("audio") or ""
            self.mark(sid, STATUS_ERROR, audio=prev, error=brief_api_error(str(exc))[:500])
            raise
        self.mark(
            sid,
            STATUS_DONE,
            audio=str(path),
            error="",
            text_at_gen=text,
            voice=voice,
        )
        return path

    def _drop_final(self) -> None:
        dest = self.final_file()
        self.final_path = ""
        self.merged_now = None
        if not dest:
            return
        for path in (dest, dest.with_suffix(".wav")):
            if path.is_file():
                try:
                    path.unlink()
                except OSError:
                    pass

    def final_file(self) -> Path | None:
        if not self.json_path:
            return None
        return self.json_path.with_name(self.json_path.stem + ".final.mp3")

    def merge_prefix(self) -> tuple[Path | None, str]:
        """Ghép từ câu đầu. Gặp lỗi hoặc chưa có audio thì dừng trước câu đó."""
        self.final_error = ""
        self.merged_now = None
        if not self.json_path:
            return None, "Chưa mở file."
        folder = audio_dir(self.json_path)
        files: list[Path] = []
        note = ""
        for i, seg in enumerate(self.segments()):
            text = (seg.get("text") or "").strip()
            if not text:
                continue
            sid = str(seg["id"])
            status = self.status_of(sid)
            audio = self.audio_of(sid) or find_clip(folder, i, sid)
            if status != STATUS_DONE or not audio:
                why = "lỗi" if status == STATUS_ERROR else "chưa có audio"
                if not files:
                    return None, f"Không ghép được. {sid} {why}."
                note = f"Ghép {len(files)} câu, dừng trước {sid} ({why})."
                break
            files.append(audio)
        if not files:
            return None, "Không có câu nào để ghép."
        if not note:
            note = f"Ghép đủ {len(files)} câu."
        dest = self.final_file()
        if dest is None:
            return None, "Chưa mở file."
        merged = _concat_ffmpeg(files, dest)
        if not merged:
            self.final_error = concat_error()
            self.final_path = ""
            self.flush_state()
            return None, self.final_error
        self.final_path = str(merged)
        self.merged_now = merged
        self.flush_state()
        return merged, f"{note} {merged.name}."

    def merge_final(self) -> Path | None:
        """Chỉ ghép khi mọi câu đã xong. Còn lỗ hổng thì để nút Ghép file xử lý."""
        for seg in self.segments():
            if not (seg.get("text") or "").strip():
                continue
            if self.status_of(str(seg["id"])) != STATUS_DONE:
                return None
        path, note = self.merge_prefix()
        if not path:
            self.final_error = note
        return path
