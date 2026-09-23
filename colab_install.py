#!/usr/bin/env python3
"""Print how to install on Colab. Use colab_setup.sh (Python 3.10 + JAX 0.4)."""

print(
    "whisper-jax does not run on Colab Python 3.13 / JAX 0.11 "
    "(jax.core.NamedShape was removed).\n"
    "In Colab run:\n"
    "  %cd /content/c-tools\n"
    "  !bash colab_setup.sh\n"
    "  !/content/ctool-venv/bin/python -c \"from app import launch_ui; launch_ui(share=True)\"\n"
)
