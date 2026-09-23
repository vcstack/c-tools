#!/usr/bin/env bash
# Colab venv: Python 3.10 + JAX 0.4 + whisper-jax + pyannote.
# No Gradio here — Colab UI is the notebook form (avoids FastAPI/Pydantic/Jinja fights).
set -euo pipefail

python3 -m pip install -q uv
uv python install 3.10
uv venv /content/ctool-venv --python 3.10 --clear
PY=/content/ctool-venv/bin/python

uv pip install --python "$PY" setuptools wheel pip
uv pip install --python "$PY" \
  "numpy<2.3" \
  "huggingface-hub==0.17.3" \
  "tokenizers==0.14.1" \
  "transformers==4.34.1" \
  python-dotenv soundfile yt-dlp cached-property

uv pip install --python "$PY" \
  --extra-index-url https://storage.googleapis.com/jax-releases/jax_cuda_releases.html \
  "jax[cuda12_pip]==0.4.26" "flax==0.8.5" \
  || uv pip install --python "$PY" "jax==0.4.26" "jaxlib==0.4.26" "flax==0.8.5"

uv pip install --python "$PY" "git+https://github.com/sanchit-gandhi/whisper-jax.git"
uv pip install --python "$PY" \
  torch==2.5.1 torchaudio==2.5.1 \
  --index-url https://download.pytorch.org/whl/cu124 \
  || uv pip install --python "$PY" torch==2.5.1 torchaudio==2.5.1

uv pip install --python "$PY" "pyannote.audio==3.1.1" "huggingface-hub==0.17.3"

"$PY" - <<'PY'
import sys
print("Python", sys.version)
import torch
print("torch", torch.__version__, "cuda", torch.cuda.is_available())
from whisper_jax import FlaxWhisperPipline  # noqa: F401
from pyannote.audio import Pipeline  # noqa: F401
import yt_dlp  # noqa: F401
print("whisper-jax + pyannote + yt-dlp OK")
PY
