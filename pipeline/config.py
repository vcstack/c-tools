"""Pipeline configuration and environment."""

from __future__ import annotations

import os
from dataclasses import dataclass

import torch
from dotenv import load_dotenv

load_dotenv()


@dataclass
class PipelineConfig:
    asr_model: str = "large-v3"
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


def resolve_device(device: str | None = None) -> str:
    if device and device != "auto":
        chosen = device
    elif torch.cuda.is_available():
        chosen = "cuda"
    else:
        chosen = "cpu"
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
    if device == "cuda":
        return "float16"
    return "int8"
