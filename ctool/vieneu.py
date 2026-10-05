"""VieNeu Cloud API (V4). Not the on-device SDK — V4 is cloud-only."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

DEFAULT_API_BASE = "https://api.vieneu.io/api/v1"
FALLBACK_VOICES = ["Ngọc Lan", "Minh Quân", "Phạm Tuyên", "Adam", "Anh Khôi"]
_v4_catalog: list[tuple[str, str]] | None = None


def api_base() -> str:
    return (os.environ.get("VIENEU_API_BASE") or DEFAULT_API_BASE).rstrip("/")


def _request(
    method: str,
    path: str,
    api_key: str,
    *,
    body: dict | None = None,
    query: dict | None = None,
    timeout: int = 180,
) -> tuple[bytes, str]:
    url = f"{api_base()}{path}"
    if query:
        url += "?" + urllib.parse.urlencode(query)
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {api_key.strip()}",
        "Accept": "*/*",
    }
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            ctype = resp.headers.get("Content-Type", "")
            return resp.read(), ctype
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:800]
        raise RuntimeError(f"VieNeu API {exc.code}: {detail or exc.reason}") from exc


def is_key_limit_error(message: str) -> bool:
    """Hết hạn mức, key sai, hoặc bị chặn — đổi token rồi chạy tiếp được."""
    text = message or ""
    low = text.lower()
    if any(f"vieneu api {code}" in low for code in ("401", "402", "403", "429")):
        return True
    needles = (
        "quota",
        "rate limit",
        "ratelimit",
        "too many request",
        "insufficient",
        "credit",
        "billing",
        "payment required",
        "usage limit",
        "hết hạn",
        "hết quota",
        "hết token",
        "invalid api",
        "unauthorized",
        "api key",
        "forbidden",
    )
    if any(needle in low for needle in needles):
        return True
    if "token" in low and any(
        word in low for word in ("limit", "exceed", "quota", "hết", "invalid", "expired")
    ):
        return True
    return False


def _choices_from_payload(parsed: Any) -> list[tuple[str, str]]:
    """(id gửi API, tên hiện trên UI)."""
    items = parsed
    if isinstance(parsed, dict):
        items = parsed.get("voices") or parsed.get("data") or parsed.get("items") or []
    choices: list[tuple[str, str]] = []
    for item in items or []:
        if isinstance(item, str):
            vid = item.strip()
            label = vid
            engine = "v4"
        elif isinstance(item, dict):
            vid = str(item.get("id") or "").strip()
            label = str(item.get("name") or vid).strip()
            engine = str(item.get("engine") or "v4").strip().lower()
        else:
            continue
        if vid and engine == "v4":
            choices.append((vid, label or vid))
    return choices


def _load_v4_catalog(api_key: str = "") -> list[tuple[str, str]]:
    global _v4_catalog
    if (api_key or "").strip():
        try:
            raw, ctype = _request("GET", "/voices", api_key, query={"engine": "v4"}, timeout=30)
            if "json" in ctype or raw[:1] in (b"{", b"["):
                choices = _choices_from_payload(json.loads(raw.decode("utf-8")))
                if choices:
                    _v4_catalog = choices
                    return choices
        except Exception:
            pass
    if _v4_catalog:
        return _v4_catalog
    try:
        url = f"{api_base()}/voices?engine=v4"
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            parsed = json.loads(resp.read().decode("utf-8"))
        _v4_catalog = _choices_from_payload(parsed)
    except Exception:
        _v4_catalog = []
    return _v4_catalog


def list_voice_catalog(api_key: str = "") -> list[tuple[str, str]]:
    choices = _load_v4_catalog(api_key)
    if choices:
        return choices
    return [(name, name) for name in FALLBACK_VOICES]


def resolve_voice(voice: str) -> str:
    """Tên trên UI hoặc id đều ra id để gửi POST /audio/speech."""
    voice = (voice or "").strip()
    if not voice:
        raise ValueError("Chưa chọn giọng.")
    if voice.startswith("clone_"):
        return voice
    choices = _load_v4_catalog()
    if not choices:
        return voice
    ids = {vid for vid, _label in choices}
    if voice in ids:
        return voice
    for vid, label in choices:
        if label == voice:
            return vid
    raise ValueError(
        f'Giọng "{voice}" không có trên VieNeu V4. Bấm Tải giọng và chọn trong danh sách.'
    )


def list_voices(api_key: str) -> list[str]:
    return [vid for vid, _label in list_voice_catalog(api_key)]


def synthesize(
    api_key: str,
    text: str,
    voice: str,
    *,
    dest: str | Path,
    response_format: str = "mp3",
) -> Path:
    text = (text or "").strip()
    if not text:
        raise ValueError("Empty TTS text")
    voice = resolve_voice(voice)
    body: dict[str, Any] = {
        "input": text,
        "voice": voice,
        "engine": "v4",
        "response_format": response_format,
    }
    raw, ctype = _request("POST", "/audio/speech", api_key, body=body)
    dest_path = Path(dest)
    if "wav" in ctype:
        dest_path = dest_path.with_suffix(".wav")
    elif "mpeg" in ctype or "mp3" in ctype:
        dest_path = dest_path.with_suffix(".mp3")
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    dest_path.write_bytes(raw)
    if dest_path.stat().st_size < 32:
        raise RuntimeError("VieNeu returned empty audio")
    return dest_path
