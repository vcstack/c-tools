#!/usr/bin/env python3
"""CLI: video/audio → transcript + speaker diarization → JSON."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure project root is importable when running as script
_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from pipeline.config import PipelineConfig, resolve_device  # noqa: E402
from pipeline.pipeline import run_pipeline  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="C-tool: extract speech transcript with speaker labels."
    )
    parser.add_argument("--input", "-i", required=True, help="Input video or audio file")
    parser.add_argument("--output", "-o", required=True, help="Output JSON path")
    parser.add_argument(
        "--model",
        default="large-v3",
        help="Whisper ASR model (default: large-v3). Use tiny/base for faster tests.",
    )
    parser.add_argument(
        "--device",
        default="auto",
        choices=["auto", "cuda", "cpu"],
        help="Compute device (default: auto)",
    )
    parser.add_argument(
        "--language",
        default=None,
        help="Source language code (optional; auto-detect if omitted)",
    )
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--min-speakers", type=int, default=1)
    parser.add_argument("--max-speakers", type=int, default=10)
    parser.add_argument(
        "--diarization-model",
        default="pyannote_3.1",
        choices=["pyannote_3.1", "pyannote_2.1", "disable"],
    )
    parser.add_argument(
        "--compute-type",
        default="default",
        help="Whisper compute type (default: float16 on GPU, int8 on CPU)",
    )
    parser.add_argument(
        "--work-dir",
        default=".cache/pipeline",
        help="Temporary working directory for extracted audio",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = PipelineConfig(
        asr_model=args.model,
        compute_type=args.compute_type,
        batch_size=args.batch_size,
        source_language=args.language,
        min_speakers=args.min_speakers,
        max_speakers=args.max_speakers,
        device=resolve_device(args.device),
        work_dir=args.work_dir,
    )
    config.diarization_model_key = args.diarization_model
    if args.diarization_model == "disable":
        config.max_speakers = 1
        config.min_speakers = 1

    try:
        run_pipeline(args.input, args.output, config)
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return 130
    except SystemExit as exc:
        print(exc, file=sys.stderr)
        return 1
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Pipeline failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
