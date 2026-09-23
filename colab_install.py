#!/usr/bin/env python3
"""Install C-tool deps with a stack whisper-jax can actually import."""

from __future__ import annotations

import subprocess
import sys


def pip_install(*args: str) -> None:
    cmd = [sys.executable, "-m", "pip", "install", *args]
    print("$", " ".join(cmd), flush=True)
    subprocess.check_call(cmd)


def main() -> None:
    pip_install("-U", "pip", "setuptools", "wheel")
    pip_install("-U", "python-dotenv", "soundfile", "gradio", "yt-dlp")
    pip_install("-U", "jax[cuda12]")
    # whisper-jax (transformers 4.34) cannot use huggingface-hub 1.x
    pip_install(
        "numpy<2.3",
        "huggingface-hub>=0.16.4,<0.18",
        "tokenizers==0.14.1",
        "transformers==4.34.1",
    )
    pip_install("git+https://github.com/sanchit-gandhi/whisper-jax.git")
    pip_install("pyannote.audio==3.1.1")
    pip_install("huggingface-hub>=0.16.4,<0.18")

    from whisper_jax import FlaxWhisperPipline  # noqa: F401

    print("whisper-jax OK")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        raise SystemExit(exc.returncode) from exc
    except ImportError as exc:
        print(f"whisper-jax import failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
