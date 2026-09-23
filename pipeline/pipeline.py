"""End-to-end ASR + diarization pipeline."""

from __future__ import annotations

import json
from pathlib import Path

from ctool.logging_setup import logger

from .alignment import build_json_payload
from .audio import extract_audio, get_duration_seconds, probe_duration_ffprobe, validate_input
from .config import (
    PipelineConfig,
    resolve_compute_type,
    resolve_device,
    resolve_hf_token,
    resolve_torch_device,
)
from .diarization import run_diarization
from .download import download_media_url, is_url
from .transcription import run_transcription


def _step(n: int, total: int, message: str) -> None:
    print(f"[{n}/{total}] {message}")


def run_pipeline(input_path: str | Path, output_path: str | Path, config: PipelineConfig) -> dict:
    total_steps = 5
    raw = str(input_path).strip()
    if is_url(raw):
        print("Downloading URL...")
        input_path = download_media_url(raw, Path("input"), cookies=config.cookies_path)
    input_path = validate_input(input_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    work_dir = Path(config.work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    wav_path = work_dir / "extracted.wav"

    device = resolve_device(config.device)
    torch_device = resolve_torch_device()
    compute_type = resolve_compute_type(device, config.compute_type)
    hf_token = config.hf_token if config.hf_token is not None else resolve_hf_token()

    _step(1, total_steps, "Loading input...")
    duration = probe_duration_ffprobe(input_path)

    _step(2, total_steps, "Extracting audio...")
    extract_audio(input_path, wav_path)
    if duration is None:
        duration = get_duration_seconds(wav_path)

    _step(3, total_steps, "Running speech recognition...")
    logger.info(
        f"ASR device: {device}, diarization: {torch_device}, "
        f"ASR: whisper-jax {config.asr_model}, compute: {compute_type}"
    )
    _audio, asr_result = run_transcription(
        str(wav_path),
        asr_model=config.asr_model,
        compute_type=compute_type,
        batch_size=config.batch_size,
        source_language=config.source_language,
        literalize_numbers=config.literalize_numbers,
        segment_duration_limit=config.segment_duration_limit,
        device=device,
    )

    _step(4, total_steps, "Running speaker diarization...")
    try:
        diarized = run_diarization(
            str(wav_path),
            asr_result,
            hf_token=hf_token,
            min_speakers=config.min_speakers,
            max_speakers=config.max_speakers,
            model_key=config.diarization_model_key,
            device=torch_device,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    except Exception as exc:
        msg = str(exc)
        if "license" in msg.lower() or "hf.co" in msg.lower():
            raise SystemExit(
                "Diarization failed. Accept pyannote model licenses on Hugging Face "
                "and set HF_TOKEN in .env. Details: " + msg
            ) from exc
        raise

    _step(5, total_steps, "Merging transcript and speakers...")
    payload = build_json_payload(
        filename=input_path.name,
        duration=duration,
        result_diarize=diarized,
    )

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"[OK] JSON written to {output_path}")
    return payload
