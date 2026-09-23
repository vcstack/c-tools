#!/usr/bin/env python3
"""Install and verify C-tool dependencies (Colab / fresh env)."""

from __future__ import annotations

import subprocess
import sys


def pip_install(*args: str) -> None:
    cmd = [sys.executable, "-m", "pip", "install", "-U", *args]
    print("$", " ".join(cmd), flush=True)
    subprocess.check_call(cmd)


def main() -> None:
    pip_install("pip", "setuptools", "wheel")

    pip_install(
        "python-dotenv",
        "soundfile",
        "gradio",
    )

    pip_install(
        "torch==2.5.1",
        "torchvision==0.20.1",
        "torchaudio==2.5.1",
        "--index-url",
        "https://download.pytorch.org/whl/cu124",
    )

    pip_install(
        "ctranslate2<=4.4.0",
        "transformers<=4.39.3",
        "faster-whisper==1.0.2",
        "pandas",
        "nltk",
        "speechbrain==0.5.16",
    )

    # R3gm forks (same stack as C-tool requirements.txt)
    pip_install("git+https://github.com/R3gm/pyannote-audio.git@3.1.1")
    # --no-deps: setup.py pins pyannote from PyPI and can break the fork install above
    pip_install(
        "git+https://github.com/R3gm/whisperX.git@cuda_12_x",
        "--no-deps",
    )

    import whisperx  # noqa: F401

    print("whisperx OK:", whisperx.__file__)


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        print("Install failed (see pip output above).", file=sys.stderr)
        raise SystemExit(exc.returncode) from exc
    except ImportError as exc:
        print(
            "pip finished but `import whisperx` failed. "
            "Runtime → Restart session, run install again.",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc
