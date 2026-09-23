"""Pipeline configuration and environment."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


def _cuda_available() -> bool:
    try:
        import torch

        return bool(torch.cuda.is_available())
    except Exception:
        return False

load_dotenv()


@dataclass
class PipelineConfig:
    asr_model: str = "large-v2"
    compute_type: str = "default"
    batch_size: int = 8
    segment_duration_limit: int = 15
    source_language: str | None = None
    literalize_numbers: bool = True
    min_speakers: int = 1
    max_speakers: int = 10
    diarization_model_key: str = "pyannote_3.1"
    device: str = "cpu"
    hf_token: str | None = None
    work_dir: str = ".cache/pipeline"


def _jax_backend() -> str | None:
    try:
        import jax

        devices = jax.devices()
        if any(d.platform == "tpu" for d in devices):
            return "tpu"
        if any(d.platform == "gpu" for d in devices):
            return "cuda"
        return "cpu"
    except Exception:
        return None


def resolve_torch_device() -> str:
    return "cuda" if _cuda_available() else "cpu"


def resolve_device(device: str | None = None) -> str:
    # whisper-jax follows JAX, not torch.cuda (Colab often has Torch CUDA + no cuDNN 8).
    if device and device != "auto":
        chosen = device
    else:
        chosen = _jax_backend() or "cpu"
    os.environ["CTOOL_DEVICE"] = chosen
    return chosen


def resolve_hf_token() -> str | None:
    token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
    if token:
        token = token.strip()
    return token or None


def resolve_compute_type(device: str, compute_type: str) -> str:
    if compute_type != "default":
        return compute_type
    if device == "tpu":
        return "bfloat16"
    if device == "cuda":
        return "float16"
    return "float32"
