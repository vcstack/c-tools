#!/usr/bin/env python3
"""Install C-tool deps for Colab: whisper-jax + pyannote (no WhisperX)."""

from __future__ import annotations

import subprocess
import sys


def pip_install(*args: str) -> None:
    cmd = [sys.executable, "-m", "pip", "install", "-U", *args]
    print("$", " ".join(cmd), flush=True)
    subprocess.check_call(cmd)


def main() -> None:
    pip_install("pip", "setuptools", "wheel")
    pip_install("python-dotenv", "soundfile", "gradio")
    pip_install("jax[cuda12]")
    pip_install("git+https://github.com/sanchit-gandhi/whisper-jax.git")
    pip_install("torch", "torchaudio")
    pip_install("pyannote.audio")

    from whisper_jax import FlaxWhisperPipline  # noqa: F401

    print("whisper-jax OK")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        raise SystemExit(exc.returncode) from exc
    except ImportError as exc:
        print("Install finished but whisper-jax import failed.", file=sys.stderr)
        raise SystemExit(1) from exc
