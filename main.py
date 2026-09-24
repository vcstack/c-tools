#!/usr/bin/env python3
"""CLI: video/audio → transcript + speaker diarization → JSON."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

os.environ["MPLBACKEND"] = "Agg"

# Ensure project root is importable when running as script
_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from ctool.runtime_env import apply_in_process  # noqa: E402

apply_in_process()

from pipeline.config import PipelineConfig, resolve_device  # noqa: E402
from pipeline.pipeline import run_pipeline  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="C-tool: extract speech transcript with speaker labels."
    )
    parser.add_argument("--input", "-i", required=True, help="Local file path or media URL")
    parser.add_argument("--output", "-o", required=True, help="Output JSON path")
    parser.add_argument(
        "--model",
        default="large-v2",
        help="whisper-jax model (tiny/base/small/medium/large-v2/large-v3).",
    )
    parser.add_argument(
        "--device",
        default="auto",
        choices=["auto", "cuda", "cpu", "tpu"],
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
        help="JAX dtype: default / float16 / bfloat16 / float32",
    )
    parser.add_argument(
        "--work-dir",
        default=".cache/pipeline",
        help="Temporary working directory for extracted audio",
    )
    parser.add_argument(
        "--cookies",
        default=None,
        help="Netscape cookies.txt for YouTube (Colab IPs often need this)",
    )
    parser.add_argument(
        "--store-dir",
        default=None,
        help="SQLite + job folders (default: Drive/ctool if mounted, else ./data/ctool)",
    )
    parser.add_argument(
        "--no-store",
        action="store_true",
        help="Skip SQLite / job-folder persist",
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
        cookies_path=args.cookies,
        store_root=args.store_dir,
        persist=not args.no_store,
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
