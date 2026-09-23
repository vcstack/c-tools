"""Speech-to-text via whisper-jax (FlaxWhisperPipline)."""

from __future__ import annotations

import soundfile as sf
from ctool.logging_setup import logger

_PIPELINE = None
_PIPELINE_KEY = None

SHORT_TO_HF = {
    "tiny": "openai/whisper-tiny",
    "base": "openai/whisper-base",
    "small": "openai/whisper-small",
    "medium": "openai/whisper-medium",
    "large": "openai/whisper-large-v2",
    "large-v2": "openai/whisper-large-v2",
    "large-v3": "openai/whisper-large-v3",
}


def resolve_model_id(asr_model: str) -> str:
    name = (asr_model or "large-v2").strip()
    if name in SHORT_TO_HF:
        return SHORT_TO_HF[name]
    if "/" in name:
        return name
    return f"openai/whisper-{name}"


def _jax_dtype(compute_type: str, device: str):
    import jax.numpy as jnp

    mapping = {
        "float16": jnp.float16,
        "bfloat16": jnp.bfloat16,
        "float32": jnp.float32,
        "int8": jnp.float16,
        "default": jnp.bfloat16 if device == "tpu" else (
            jnp.float16 if device == "cuda" else jnp.float32
        ),
    }
    return mapping.get(compute_type, mapping["default"])


def get_pipeline(model_id: str, compute_type: str, batch_size: int, device: str):
    global _PIPELINE, _PIPELINE_KEY
    key = (model_id, compute_type, batch_size, device)
    if _PIPELINE is not None and _PIPELINE_KEY == key:
        return _PIPELINE

    from whisper_jax import FlaxWhisperPipline

    dtype = _jax_dtype(compute_type, device)
    logger.info(f"Loading whisper-jax {model_id} dtype={dtype} batch_size={batch_size}")
    _PIPELINE = FlaxWhisperPipline(model_id, dtype=dtype, batch_size=max(1, int(batch_size)))
    _PIPELINE_KEY = key
    return _PIPELINE


def _chunk_times(chunk: dict, fallback_end: float) -> tuple[float, float]:
    ts = chunk.get("timestamp")
    if not ts:
        return 0.0, float(fallback_end)
    start, end = ts[0], ts[1]
    start_f = float(start or 0.0)
    end_f = float(end) if end is not None else float(fallback_end)
    if end_f < start_f:
        end_f = start_f
    return start_f, end_f


def transcribe_speech(
    audio_wav: str,
    asr_model: str,
    compute_type: str,
    batch_size: int,
    source_language: str | None,
    device: str = "cpu",
) -> dict:
    """
    Transcribe in the original spoken language (task=transcribe, no translation).

    Returns {"language": str|None, "segments": [{"start","end","text"}, ...]}.
    """
    model_id = resolve_model_id(asr_model)
    duration = float(sf.info(audio_wav).duration)
    pipe = get_pipeline(model_id, compute_type, batch_size, device)

    call_kwargs = {"task": "transcribe", "return_timestamps": True}
    if source_language:
        call_kwargs["language"] = source_language

    try:
        outputs = pipe(audio_wav, **call_kwargs)
    except TypeError:
        outputs = pipe(audio_wav, task="transcribe", return_timestamps=True)

    chunks = outputs.get("chunks") or []
    segments = []
    for chunk in chunks:
        text = (chunk.get("text") or "").strip()
        if not text:
            continue
        start, end = _chunk_times(chunk, duration)
        segments.append({"start": start, "end": end, "text": text})

    if not segments:
        whole = (outputs.get("text") or "").strip()
        if whole:
            segments = [{"start": 0.0, "end": duration, "text": whole}]

    if not segments:
        raise ValueError("No speech detected in the audio.")

    language = outputs.get("language") or source_language
    logger.info(f"whisper-jax segments: {len(segments)} language={language}")
    return {"language": language, "segments": segments}
