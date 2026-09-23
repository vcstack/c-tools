"""Speaker diarization via pyannote / WhisperX."""

from __future__ import annotations

from ctool.speech_segmentation import diarization_models, diarize_speech


def run_diarization(
    audio_wav: str,
    asr_result: dict,
    *,
    hf_token: str | None,
    min_speakers: int,
    max_speakers: int,
    model_key: str = "pyannote_3.1",
):
    """
    Assign speakers to ASR segments using pyannote + whisperx.assign_word_speakers.

    model_key: pyannote_3.1 | pyannote_2.1 | disable
    """
    model_name = diarization_models.get(model_key, diarization_models["pyannote_3.1"])
    if model_key != "disable" and max(min_speakers, max_speakers) > 1 and not hf_token:
        raise ValueError(
            "HF_TOKEN is required for pyannote diarization with multiple speakers. "
            "Set HF_TOKEN in .env or use --max-speakers 1 to skip diarization."
        )
    token = hf_token or ""
    return diarize_speech(
        audio_wav,
        asr_result,
        min_speakers,
        max_speakers,
        token,
        model_name,
    )
