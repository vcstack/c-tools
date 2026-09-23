"""Process env for Colab: matplotlib backend + cuDNN 8.9 for JAX 0.4.26."""

from __future__ import annotations

import os
import sys
from pathlib import Path

CUDNN89_LIB = Path("/content/cudnn89/nvidia/cudnn/lib")
VENV_SITE = Path("/content/ctool-venv/lib/python3.10/site-packages")


def extra_lib_dirs() -> list[str]:
    dirs: list[str] = []
    for path in (
        CUDNN89_LIB,
        VENV_SITE / "nvidia" / "cudnn" / "lib",
        VENV_SITE / "nvidia" / "cuda_nvrtc" / "lib",
        VENV_SITE / "nvidia" / "cuda_runtime" / "lib",
        VENV_SITE / "nvidia" / "cublas" / "lib",
    ):
        if path.is_dir():
            dirs.append(str(path))
    return dirs


def _has_cudnn8(lib_dirs: list[str] | None = None) -> bool:
    names = []
    for folder in lib_dirs or extra_lib_dirs():
        names.append(str(Path(folder) / "libcudnn.so.8"))
    names.extend(["libcudnn.so.8", "libcudnn.so"])
    try:
        import ctypes
    except Exception:
        return False
    for name in names:
        try:
            ctypes.CDLL(name)
            return True
        except OSError:
            continue
    return False


def pipeline_env(base: dict[str, str] | None = None) -> dict[str, str]:
    env = dict(base if base is not None else os.environ)
    env["MPLBACKEND"] = "Agg"
    env.setdefault("XLA_PYTHON_CLIENT_PREALLOCATE", "false")
    extras = extra_lib_dirs()
    if extras:
        current = env.get("LD_LIBRARY_PATH", "")
        parts = [p for p in extras if p and p not in current.split(":")]
        if parts:
            env["LD_LIBRARY_PATH"] = ":".join(parts + ([current] if current else []))
    lib_dirs = [p for p in env.get("LD_LIBRARY_PATH", "").split(":") if p]
    if not _has_cudnn8(lib_dirs):
        env.setdefault("JAX_PLATFORMS", "cpu")
    return env


def apply_in_process(*, reexec: bool = True) -> None:
    os.environ["MPLBACKEND"] = "Agg"
    os.environ.setdefault("XLA_PYTHON_CLIENT_PREALLOCATE", "false")
    extras = extra_lib_dirs()
    current = os.environ.get("LD_LIBRARY_PATH", "")
    parts = [p for p in extras if p not in current.split(":")]
    if parts:
        os.environ["LD_LIBRARY_PATH"] = ":".join(parts + ([current] if current else []))
        if reexec and not os.environ.get("CTOOL_LD_READY"):
            os.environ["CTOOL_LD_READY"] = "1"
            os.execv(sys.executable, [sys.executable, *sys.argv])
    if not _has_cudnn8():
        os.environ.setdefault("JAX_PLATFORMS", "cpu")
