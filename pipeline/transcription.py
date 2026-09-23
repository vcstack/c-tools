"""Speech-to-text via SoniTranslate WhisperX integration."""

from __future__ import annotations

from sonitr_st.logging_setup import configure_logging_libs, logger
from sonitr_st.speech_segmentation import align_speech, transcribe_speech

configure_logging_libs()


def run_transcription(
    audio_wav: str,
    *,
    asr_model: str,
    compute_type: str,
    batch_size: int,
    source_language: str | None,
    literalize_numbers: bool,
    segment_duration_limit: int,
    align: bool = True,
):
    """
    Returns (audio_array, result_dict) where result contains segments with timestamps.
    """
    audio, result = transcribe_speech(
        audio_wav,
        asr_model,
        compute_type,
        batch_size,
        source_language,
        literalize_numbers,
        segment_duration_limit,
    )
    if not result.get("segments"):
        raise ValueError("No speech detected in the audio.")

    if align:
        try:
            result = align_speech(audio, result)
        except ValueError as exc:
            logger.warning(f"Alignment skipped: {exc}")
        except Exception as exc:
            logger.warning(f"Alignment failed ({exc}); using ASR segment timestamps.")

    return audio, result
