#!/usr/bin/env bash
# Colab venv: Python 3.10 + JAX 0.4 + whisper-jax + pyannote.
# No Gradio here — Colab UI is the notebook form (avoids FastAPI/Pydantic/Jinja fights).
set -euo pipefail

python3 -m pip install -q uv
uv python install 3.10
uv venv /content/ctool-venv --python 3.10 --clear
PY=/content/ctool-venv/bin/python

uv pip install --python "$PY" setuptools wheel pip
# pyannote 3.1 still uses np.NaN (removed in NumPy 2)
uv pip install --python "$PY" \
  "numpy>=1.26.4,<2" \
  "huggingface-hub==0.17.3" \
  "tokenizers==0.14.1" \
  "transformers==4.34.1" \
  python-dotenv soundfile yt-dlp cached-property

# jax_cuda_releases.html is a find-links page, not a PEP 503 index.
# Do not pin jaxlib==0.4.26 here — the CUDA extra needs jaxlib==0.4.26+cuda12.cudnn89.
uv pip install --python "$PY" \
  --find-links https://storage.googleapis.com/jax-releases/jax_cuda_releases.html \
  "jax[cuda12_pip]==0.4.26" "flax==0.8.4" \
  || uv pip install --python "$PY" "jax==0.4.26" "jaxlib==0.4.26" "flax==0.8.4"

uv pip install --python "$PY" "git+https://github.com/sanchit-gandhi/whisper-jax.git"
uv pip install --python "$PY" \
  torch==2.5.1 torchaudio==2.5.1 \
  --index-url https://download.pytorch.org/whl/cu124 \
  || uv pip install --python "$PY" torch==2.5.1 torchaudio==2.5.1

uv pip install --python "$PY" "pyannote.audio==3.1.1"
# pyannote may pull newer hub / numpy; pin back
uv pip install --python "$PY" "huggingface-hub==0.17.3" "numpy>=1.26.4,<2"

"$PY" - <<'PY'
import sys
print("Python", sys.version)
import numpy
print("numpy", numpy.__version__)
import jax
print("jax", jax.__version__, "backend", jax.default_backend())
import torch
print("torch", torch.__version__, "cuda", torch.cuda.is_available())
from whisper_jax import FlaxWhisperPipline  # noqa: F401
from pyannote.audio import Pipeline  # noqa: F401
import yt_dlp  # noqa: F401
print("whisper-jax + pyannote + yt-dlp OK")
PY
