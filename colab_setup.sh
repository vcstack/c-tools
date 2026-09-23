#!/usr/bin/env bash
# Colab: whisper-jax needs Python 3.10 + JAX 0.4.x (not Colab's 3.13 / JAX 0.11).
set -euo pipefail
python3 -m pip install -q uv
uv python install 3.10
uv venv /content/ctool-venv --python 3.10 --clear
PY=/content/ctool-venv/bin/python

uv pip install --python "$PY" setuptools wheel pip
uv pip install --python "$PY" \
  "numpy<2.3" \
  "huggingface-hub>=0.16.4,<0.18" \
  "tokenizers==0.14.1" \
  "transformers==4.34.1" \
  python-dotenv soundfile "gradio==3.50.2" yt-dlp

uv pip install --python "$PY" \
  --extra-index-url https://storage.googleapis.com/jax-releases/jax_cuda_releases.html \
  "jax[cuda12_pip]==0.4.26" \
  flax cached-property \
  || uv pip install --python "$PY" "jax==0.4.26" "jaxlib==0.4.26" flax cached-property

uv pip install --python "$PY" "git+https://github.com/sanchit-gandhi/whisper-jax.git"
uv pip install --python "$PY" \
  torch==2.5.1 torchaudio==2.5.1 \
  --index-url https://download.pytorch.org/whl/cu124 \
  || uv pip install --python "$PY" torch torchaudio
uv pip install --python "$PY" "pyannote.audio==3.1.1" "huggingface-hub>=0.16.4,<0.18"

"$PY" -c "import sys, torch; from whisper_jax import FlaxWhisperPipline; print(sys.version); print('torch', torch.__version__); print('whisper-jax OK')"
