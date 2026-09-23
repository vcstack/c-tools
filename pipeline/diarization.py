"""Speaker diarization via pyannote + overlap merge."""

from __future__ import annotations

from ctool.diarize import DIARIZATION_MODELS, run_pyannote
from pipeline.alignment import merge_transcript_and_speakers


def run_diarization(
    audio_wav: str,
    asr_result: dict,
    *,
    hf_token: str | None,
    min_speakers: int,
    max_speakers: int,
    model_key: str = "pyannote_3.1",
    device: str = "cpu",
):
    """
    Label ASR segments with speakers.

    If a transcript segment overlaps multiple speakers, assign the speaker
    with the largest temporal overlap (deterministic).
    """
    model_name = DIARIZATION_MODELS.get(model_key, DIARIZATION_MODELS["pyannote_3.1"])
    if model_key == "disable" or max(min_speakers, max_speakers) <= 1:
        labeled = [{**seg, "speaker": "SPEAKER_00"} for seg in asr_result.get("segments", [])]
        return {"segments": labeled, "language": asr_result.get("language")}

    if not hf_token:
        raise ValueError(
            "HF_TOKEN is required for pyannote when max_speakers > 1. "
            "Set HF_TOKEN or use --max-speakers 1."
        )

    regions = run_pyannote(
        audio_wav,
        hf_token=hf_token,
        min_speakers=min_speakers,
        max_speakers=max_speakers,
        model_name=model_name,
        device=device,
    )
    return merge_transcript_and_speakers(asr_result, regions)
