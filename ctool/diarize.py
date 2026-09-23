"""Speaker diarization via pyannote (no WhisperX)."""

from __future__ import annotations

from ctool.logging_setup import logger

DIARIZATION_MODELS = {
    "pyannote_3.1": "pyannote/speaker-diarization-3.1",
    "pyannote_2.1": "pyannote/speaker-diarization@2.1",
    "disable": "",
}


def _license_error(model_name: str) -> ValueError:
    if "3.1" in model_name:
        return ValueError(
            "Accept pyannote 3.1 licenses on Hugging Face: "
            "https://huggingface.co/pyannote/speaker-diarization-3.1 "
            "and https://huggingface.co/pyannote/segmentation-3.0 "
            "then set HF_TOKEN."
        )
    return ValueError(
        "Accept pyannote licenses on Hugging Face: "
        "https://huggingface.co/pyannote/speaker-diarization "
        "and https://huggingface.co/pyannote/segmentation "
        "then set HF_TOKEN."
    )


def run_pyannote(
    audio_wav: str,
    *,
    hf_token: str,
    min_speakers: int,
    max_speakers: int,
    model_name: str,
    device: str,
) -> list[tuple[float, float, str]]:
    """Return (start, end, speaker) regions."""
    try:
        from pyannote.audio import Pipeline
    except ImportError as exc:
        raise RuntimeError("pyannote.audio is not installed.") from exc

    try:
        try:
            pipeline = Pipeline.from_pretrained(model_name, token=hf_token or None)
        except TypeError:
            pipeline = Pipeline.from_pretrained(model_name, use_auth_token=hf_token or None)
        if pipeline is None:
            raise _license_error(model_name)
        if device == "cuda":
            import torch

            pipeline.to(torch.device("cuda"))
        annotation = pipeline(
            audio_wav,
            min_speakers=min_speakers,
            max_speakers=max_speakers,
        )
    except Exception as error:
        msg = str(error)
        if "NoneType" in msg or "gated" in msg.lower() or "401" in msg or "403" in msg:
            raise _license_error(model_name) from error
        raise

    regions: list[tuple[float, float, str]] = []
    for turn, _, speaker in annotation.itertracks(yield_label=True):
        regions.append((float(turn.start), float(turn.end), str(speaker)))
    logger.info(f"pyannote regions: {len(regions)}")
    return regions
