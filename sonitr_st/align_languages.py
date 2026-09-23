"""WhisperX alignment language maps (reused from SoniTranslate)."""

from pathlib import Path
import sys

_ROOT = Path(__file__).resolve().parents[1]
_SONITR_ROOT = _ROOT / "SoniTranslate"
if _SONITR_ROOT.is_dir():
    sonitr_path = str(_SONITR_ROOT)
    if sonitr_path not in sys.path:
        sys.path.insert(0, sonitr_path)
    from soni_translate.language_configuration import EXTRA_ALIGN, INVERTED_LANGUAGES
else:
    EXTRA_ALIGN = {}
    INVERTED_LANGUAGES = {}

__all__ = ["EXTRA_ALIGN", "INVERTED_LANGUAGES"]
