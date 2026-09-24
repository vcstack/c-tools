"""Speech-to-text via whisper-jax."""

from __future__ import annotations

from ctool.asr import transcribe_speech
from ctool.logging_setup import configure_logging_libs

configure_logging_libs()


def run_transcription(
    audio_wav: str,
    *,
    asr_model: str,
    compute_type: str,
    batch_size: int,
    source_language: str | None,
    literalize_numbers: bool = True,
    segment_duration_limit: int = 15,
    align: bool = True,
    device: str = "cpu",
    chunk_boundaries: list[float] | None = None,
    work_dir: str | None = None,
):
    """Returns (None, result_dict) with segment timestamps. No translation."""
    del literalize_numbers, segment_duration_limit, align

    def _once(path: str) -> dict:
        return transcribe_speech(
            path,
            asr_model,
            compute_type,
            batch_size,
            source_language,
            device=device,
        )

    if chunk_boundaries:
        from pipeline.chunking import transcribe_chunked

        result = transcribe_chunked(
            audio_wav,
            chunk_boundaries,
            transcribe_fn=_once,
            work_dir=work_dir or ".cache/pipeline/chunks",
        )
    else:
        result = _once(audio_wav)
    return None, result
