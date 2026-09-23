"""Media helpers: extensions, FFmpeg extraction, duration."""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

import soundfile as sf

from ctool.media_utils import run_command

VIDEO_EXTENSIONS = {".mp4", ".mkv", ".mov", ".avi", ".webm", ".m4v", ".mpeg", ".mpg", ".wmv", ".flv"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac", ".opus", ".wma", ".aiff", ".aif"}


def is_video(path: str | Path) -> bool:
    return Path(path).suffix.lower() in VIDEO_EXTENSIONS


def is_audio(path: str | Path) -> bool:
    return Path(path).suffix.lower() in AUDIO_EXTENSIONS


def validate_input(path: str | Path) -> Path:
    p = Path(path).resolve()
    if not p.is_file():
        raise FileNotFoundError(f"Input file not found: {p}")
    ext = p.suffix.lower()
    if ext not in VIDEO_EXTENSIONS | AUDIO_EXTENSIONS:
        raise ValueError(
            f"Unsupported extension {ext!r}. Supported: "
            f"{sorted(VIDEO_EXTENSIONS | AUDIO_EXTENSIONS)}"
        )
    return p


def get_duration_seconds(audio_path: str | Path) -> float:
    info = sf.info(str(audio_path))
    return float(info.duration)


def extract_audio(input_path: str | Path, output_wav: str | Path) -> Path:
    """Extract/normalize to 44.1kHz stereo PCM WAV."""
    input_path = Path(input_path)
    output_wav = Path(output_wav)
    output_wav.parent.mkdir(parents=True, exist_ok=True)

    if is_audio(input_path) and input_path.suffix.lower() == ".wav":
        cmd = (
            f'ffmpeg -y -i "{input_path}" -acodec pcm_s16le -ar 44100 -ac 2 '
            f'"{output_wav}"'
        )
    else:
        cmd = (
            f'ffmpeg -y -i "{input_path}" -vn -acodec pcm_s16le -ar 44100 -ac 2 '
            f'"{output_wav}"'
        )
    run_command(cmd)
    if not output_wav.is_file() or output_wav.stat().st_size == 0:
        raise RuntimeError(f"FFmpeg did not produce audio: {output_wav}")
    return output_wav


def probe_duration_ffprobe(media_path: str | Path) -> float | None:
    """Duration from container metadata (works before extraction)."""
    cmd = shlex.split(
        f'ffprobe -v error -show_entries format=duration -of json "{media_path}"'
    )
    sub_params = {
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "creationflags": subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    }
    proc = subprocess.Popen(cmd, **sub_params)
    out, _ = proc.communicate()
    if proc.returncode != 0:
        return None
    try:
        data = json.loads(out.decode("utf-8"))
        return float(data["format"]["duration"])
    except (KeyError, ValueError, json.JSONDecodeError):
        return None
