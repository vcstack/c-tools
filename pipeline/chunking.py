"""Long-audio STT: fixed part count, adjustable cut boundaries, overlap merge."""

from __future__ import annotations

import math
import re
from difflib import SequenceMatcher
from pathlib import Path

from ctool.logging_setup import logger
from ctool.media_utils import run_command
from pipeline.audio import probe_duration_ffprobe
from pipeline.download import is_url

CHUNK_TARGET_SEC = 8 * 60
CHUNK_THRESHOLD_SEC = 8 * 60
CHUNK_MAX_SEC = 10 * 60
CHUNK_MIN_SEC = 60
OVERLAP_SEC = 3.0
MAX_CUT_SLIDERS = 23


def probe_media_duration(
    source: str | Path,
    cookies_path: str | Path | None = None,
) -> float | None:
    """Duration in seconds from local file or media URL (yt-dlp metadata)."""
    raw = str(source).strip()
    if is_url(raw):
        try:
            import yt_dlp

            opts: dict = {"quiet": True, "noplaylist": True, "skip_download": True}
            if cookies_path and Path(cookies_path).is_file():
                opts["cookiefile"] = str(cookies_path)
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(raw, download=False)
            dur = info.get("duration")
            return float(dur) if dur is not None else None
        except Exception:
            return None
    return probe_duration_ffprobe(raw)


def needs_chunking(duration_sec: float) -> bool:
    return float(duration_sec) > CHUNK_THRESHOLD_SEC


def part_count(duration_sec: float) -> int:
    duration_sec = float(duration_sec)
    if not needs_chunking(duration_sec):
        return 1
    return max(2, int(math.ceil(duration_sec / CHUNK_TARGET_SEC)))


def default_boundaries(duration_sec: float) -> list[float]:
    """Internal cut times (seconds); len = part_count - 1."""
    duration_sec = float(duration_sec)
    if not needs_chunking(duration_sec):
        return []
    n = part_count(duration_sec)
    step = duration_sec / n
    return [step * i for i in range(1, n)]


def format_mmss(seconds: float) -> str:
    s = max(0.0, float(seconds))
    m = int(s // 60)
    sec = s - m * 60
    return f"{m}:{sec:05.2f}"


def validate_boundaries(duration_sec: float, boundaries: list[float]) -> list[float]:
    duration_sec = float(duration_sec)
    if not needs_chunking(duration_sec):
        return []
    expected = len(default_boundaries(duration_sec))
    cuts = sorted(float(x) for x in boundaries)
    if len(cuts) != expected:
        raise ValueError(
            f"Cần đúng {expected} mép cắt (file ~{part_count(duration_sec)} phần), "
            f"đang có {len(cuts)}."
        )
    edges = [0.0] + cuts + [duration_sec]
    for i in range(len(edges) - 1):
        length = edges[i + 1] - edges[i]
        if length < CHUNK_MIN_SEC - 0.01:
            raise ValueError(
                f"Phần {i + 1} quá ngắn ({length:.0f}s). "
                f"Mỗi phần tối thiểu {CHUNK_MIN_SEC}s."
            )
        if length > CHUNK_MAX_SEC + 0.01:
            raise ValueError(
                f"Phần {i + 1} quá dài ({length:.0f}s). "
                f"Mỗi phần tối đa {CHUNK_MAX_SEC // 60} phút (kéo mép cắt)."
            )
    return cuts


def boundary_slider_limits(
    duration_sec: float,
    boundaries: list[float],
    index: int,
) -> tuple[float, float]:
    """Min/max for slider at cut index (0-based)."""
    duration_sec = float(duration_sec)
    cuts = sorted(float(x) for x in boundaries)
    k = len(cuts)
    prev_edge = cuts[index - 1] if index > 0 else 0.0
    next_edge = cuts[index + 1] if index < k - 1 else duration_sec
    lo = prev_edge + CHUNK_MIN_SEC
    hi = min(prev_edge + CHUNK_MAX_SEC, next_edge - CHUNK_MIN_SEC)
    if index == k - 1:
        hi = min(hi, duration_sec - CHUNK_MIN_SEC)
    if lo > hi:
        lo, hi = hi, lo
    return lo, hi


def build_chunk_specs(
    duration_sec: float,
    boundaries: list[float],
    overlap_sec: float = OVERLAP_SEC,
) -> list[tuple[float, float, float]]:
    """
    Return list of (ffmpeg_ss, ffmpeg_duration, global_offset_sec).
    global_offset_sec maps local t=0 to timeline of the full file.
    """
    duration_sec = float(duration_sec)
    cuts = validate_boundaries(duration_sec, boundaries)
    edges = [0.0] + cuts + [duration_sec]
    specs: list[tuple[float, float, float]] = []
    n = len(edges) - 1
    for i in range(n):
        chunk_start = edges[i]
        chunk_end = edges[i + 1]
        ss = max(0.0, chunk_start - (overlap_sec if i > 0 else 0.0))
        end = min(
            duration_sec,
            chunk_end + (overlap_sec if i < n - 1 else 0.0),
        )
        dur = end - ss
        specs.append((ss, dur, ss))
    return specs


def extract_wav_segment(
    source_wav: str | Path,
    dest_wav: str | Path,
    start_sec: float,
    duration_sec: float,
) -> Path:
    source_wav = Path(source_wav)
    dest_wav = Path(dest_wav)
    dest_wav.parent.mkdir(parents=True, exist_ok=True)
    cmd = (
        f'ffmpeg -y -ss {start_sec:.3f} -t {duration_sec:.3f} -i "{source_wav}" '
        f'-acodec pcm_s16le -ar 16000 -ac 1 "{dest_wav}"'
    )
    run_command(cmd)
    if not dest_wav.is_file() or dest_wav.stat().st_size == 0:
        raise RuntimeError(f"FFmpeg chunk extract failed: {dest_wav}")
    return dest_wav


def extract_preview_clip(
    media_path: str | Path,
    dest_wav: str | Path,
    center_sec: float,
    window_sec: float = 10.0,
) -> Path:
    """~window_sec around center_sec for UI preview."""
    media_path = Path(media_path)
    dest_wav = Path(dest_wav)
    dest_wav.parent.mkdir(parents=True, exist_ok=True)
    half = window_sec / 2.0
    ss = max(0.0, float(center_sec) - half)
    cmd = (
        f'ffmpeg -y -ss {ss:.3f} -t {window_sec:.3f} -i "{media_path}" '
        f'-vn -acodec pcm_s16le -ar 16000 -ac 1 "{dest_wav}"'
    )
    run_command(cmd)
    return dest_wav


def _norm_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower().strip())


def _texts_redundant(a: str, b: str) -> bool:
    na, nb = _norm_text(a), _norm_text(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    if na in nb or nb in na:
        return True
    return SequenceMatcher(None, na, nb).ratio() >= 0.72


def merge_chunk_segments(segments: list[dict]) -> list[dict]:
    """Drop duplicate / truncated segments from overlap regions."""
    if not segments:
        return []
    ordered = sorted(segments, key=lambda s: (float(s["start"]), float(s["end"])))
    out: list[dict] = []
    for seg in ordered:
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        start, end = float(seg["start"]), float(seg["end"])
        if end <= start:
            continue
        candidate = {"start": start, "end": end, "text": text}
        if not out:
            out.append(candidate)
            continue
        prev = out[-1]
        if start >= prev["end"] - 0.05:
            out.append(candidate)
            continue
        if _texts_redundant(prev["text"], text):
            if len(text) > len(prev["text"]):
                out[-1] = candidate
            continue
        if end <= prev["end"] + 0.2:
            continue
        prev["end"] = min(prev["end"], start)
        out.append(candidate)
    return out


def transcribe_chunked(
    audio_wav: str,
    boundaries: list[float],
    *,
    transcribe_fn,
    work_dir: str | Path,
) -> dict:
    """
    transcribe_fn(wav_path) -> {"language", "segments"}.
    """
    import soundfile as sf

    duration = float(sf.info(audio_wav).duration)
    specs = build_chunk_specs(duration, boundaries)
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    merged: list[dict] = []
    language = None
    for idx, (ss, dur, offset) in enumerate(specs):
        chunk_path = work_dir / f"chunk_{idx:03d}.wav"
        extract_wav_segment(audio_wav, chunk_path, ss, dur)
        logger.info(f"STT chunk {idx + 1}/{len(specs)} ss={ss:.1f}s dur={dur:.1f}s")
        part = transcribe_fn(str(chunk_path))
        language = language or part.get("language")
        for seg in part.get("segments") or []:
            text = (seg.get("text") or "").strip()
            if not text:
                continue
            merged.append(
                {
                    "start": float(seg["start"]) + offset,
                    "end": float(seg["end"]) + offset,
                    "text": text,
                }
            )
        try:
            chunk_path.unlink(missing_ok=True)
        except OSError:
            pass

    segments = merge_chunk_segments(merged)
    if not segments:
        raise ValueError("No speech detected in the audio (chunked STT).")
    logger.info(f"Chunked STT merged segments: {len(segments)}")
    return {"language": language, "segments": segments}
